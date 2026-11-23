"""One CallSession per phone call: speaks, listens, decides, acts."""
import asyncio
import base64
import json
import logging
import time

import numpy as np
from fastapi import WebSocket, WebSocketDisconnect

from . import config, intent, messages, shopify, speech

log = logging.getLogger("session")

CHUNK_BYTES = 3200  # multiple of 320 bytes (20 ms of 8 kHz 16-bit audio)


class CallSession:
    def __init__(self, ws: WebSocket, pending_calls: dict, on_hangup):
        self.ws = ws
        self.pending_calls = pending_calls
        self.on_hangup = on_hangup
        self.call_sid = None
        self.stream_sid = None
        self.order = None
        self.lang = "hi-IN"
        self.decided = False
        self.repeats = 0
        self.done = False
        self.ignore_until = 0.0
        self.t_open = time.monotonic()  # when Exotel connected to us
        self._reset_listening(time.monotonic())

    # ---------- receiving ----------
    async def run(self):
        hung_up = False
        try:
            while not self.done:
                msg = json.loads(await self.ws.receive_text())
                event = msg.get("event")
                if event == "start":
                    await self._on_start(msg)
                elif event == "media" and self.order:
                    await self._on_media(base64.b64decode(msg["media"]["payload"]))
                elif event == "stop":
                    hung_up = True
                    break
        except (WebSocketDisconnect, RuntimeError):
            hung_up = True
        if hung_up and self.order and not self.decided:
            log.info("Customer hung up before deciding")
            await self.on_hangup(self.order, self.call_sid, "hung-up")

    async def _on_start(self, msg: dict):
        start = msg.get("start", {})
        self.stream_sid = msg.get("stream_sid") or start.get("stream_sid")
        call_sid = start.get("call_sid") or msg.get("call_sid")
        self.call_sid = call_sid
        self.order = self.pending_calls.get(call_sid)
        if not self.order:
            log.error("No pending order for call_sid=%s", call_sid)
            self.done = True
            return
        self.lang = self.order["language"]
        t_start = time.monotonic()
        log.info("Call started for order %s in %s (start event %.1fs after the WebSocket opened)",
                 self.order["number"], self.lang, t_start - self.t_open)
        await self._speak(messages.build_greeting(self.order))
        log.info("Greeting audio sent %.1fs after the start event", time.monotonic() - t_start)
        # While the customer listens to the greeting, prepare the other phrases.
        for key in ("reprompt", "confirmed", "cancelled", "give_up", "error"):
            speech.prefetch(messages.get(self.lang, key), self.lang)

    # ---------- speaking ----------
    async def _speak(self, text: str) -> float:
        pcm = await speech.synthesize(text, self.lang)
        padded = pcm + b"\x00" * (-len(pcm) % 320)
        for i in range(0, len(padded), CHUNK_BYTES):
            chunk = padded[i : i + CHUNK_BYTES]
            await self.ws.send_text(json.dumps({
                "event": "media",
                "stream_sid": self.stream_sid,
                "media": {"payload": base64.b64encode(chunk).decode()},
            }))
        duration = len(pcm) / (config.SAMPLE_RATE * 2)
        # Ignore the line while our own voice plays, then start listening.
        self.ignore_until = time.monotonic() + duration + 0.4
        self._reset_listening(self.ignore_until)
        return duration

    def _reset_listening(self, started_at: float):
        self.buf = bytearray()
        self.speech_started = False
        self.last_voice = 0.0
        self.utterance_start = 0.0
        self.listen_start = started_at

    # ---------- listening (simple energy-based voice detection) ----------
    async def _on_media(self, chunk: bytes):
        now = time.monotonic()
        if now < self.ignore_until or not chunk:
            return
        samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)
        rms = float(np.sqrt(np.mean(samples ** 2))) if samples.size else 0.0
        voiced = rms > config.SPEECH_RMS_THRESHOLD

        if voiced:
            if not self.speech_started:
                self.speech_started = True
                self.utterance_start = now
            self.last_voice = now
            self.buf += chunk
        elif self.speech_started:
            self.buf += chunk
        elif now - self.listen_start > config.NO_SPEECH_TIMEOUT:
            await self._handle_answer("")  # silence counts as an unclear answer
            return

        if self.speech_started:
            silent_for = now - self.last_voice
            too_long = now - self.utterance_start > config.MAX_UTTERANCE_SECONDS
            if silent_for > config.SILENCE_END_SECONDS or too_long:
                pcm = bytes(self.buf)
                if len(pcm) / (config.SAMPLE_RATE * 2) < config.MIN_UTTERANCE_SECONDS:
                    self._reset_listening(now)  # just a click or noise
                    return
                text = ""
                try:
                    text = await speech.transcribe(pcm, self.lang)
                except Exception:
                    log.exception("Speech-to-text failed")
                await self._handle_answer(text)

    # ---------- deciding and acting ----------
    async def _handle_answer(self, text: str):
        answer = intent.classify(text, self.lang)
        log.info("Order %s heard=%r -> %s", self.order["number"], text, answer)

        if answer == "yes":
            await self._finish(shopify.confirm_order, messages.get(self.lang, "confirmed"))
        elif answer == "no":
            await self._finish(shopify.cancel_order, messages.get(self.lang, "cancelled"))
        else:
            self.repeats += 1
            if self.repeats > config.MAX_REPEATS:
                # no clear "yes" even after repeating -> cancel
                await self._finish(shopify.cancel_order, messages.get(self.lang, "give_up"))
            else:
                await self._speak(messages.get(self.lang, "reprompt"))

    async def _finish(self, action, message: str):
        self.decided = True
        self.order["finished"] = True
        try:
            await action(self.order["id"])
        except Exception:
            log.exception("Shopify update failed for order %s", self.order["id"])
            message = messages.get(self.lang, "error")
        duration = await self._speak(message)
        await asyncio.sleep(duration + 0.5)  # let the audio finish before hanging up
        self.done = True