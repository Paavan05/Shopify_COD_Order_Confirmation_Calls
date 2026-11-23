"""Speech-to-text and text-to-speech. Only this file knows about Sarvam, so you
can swap the provider by rewriting these functions.

Speed tricks used here:
- one shared HTTP client, so connections to Sarvam are reused (no new TLS handshake each time)
- prefetch(): start generating audio before it is needed (e.g. while the phone is still ringing)
- identical requests share one in-flight/finished result, so nothing is generated twice
"""
import asyncio
import base64
import io
import logging
import time
import wave

import httpx

from . import config

log = logging.getLogger("speech")

_STT_URL = "https://api.sarvam.ai/speech-to-text"
_TTS_URL = "https://api.sarvam.ai/text-to-speech"

_client: httpx.AsyncClient | None = None
_tts_tasks: dict[tuple[str, str], asyncio.Task] = {}
MAX_CACHED_AUDIOS = 200  # greetings differ per order, so keep the cache bounded


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30)
    return _client


def _pcm_to_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(config.SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def _check(resp: httpx.Response, what: str) -> None:
    if resp.status_code >= 400:
        log.error("Sarvam %s error %s: %s", what, resp.status_code, resp.text)
    resp.raise_for_status()


async def transcribe(pcm: bytes, lang: str) -> str:
    """8 kHz 16-bit mono PCM -> text in the given language (e.g. 'gu-IN')."""
    started = time.monotonic()
    resp = await _get_client().post(
        _STT_URL,
        headers={"api-subscription-key": config.SARVAM_API_KEY},
        files={"file": ("audio.wav", _pcm_to_wav(pcm), "audio/wav")},
        data={"model": "saarika:v2.5", "language_code": lang},
    )
    _check(resp, "speech-to-text")
    log.info("speech-to-text took %.2fs", time.monotonic() - started)
    return resp.json().get("transcript", "")


async def _synthesize_uncached(text: str, lang: str) -> bytes:
    started = time.monotonic()
    resp = await _get_client().post(
        _TTS_URL,
        headers={"api-subscription-key": config.SARVAM_API_KEY},
        json={
            "text": text,
            "target_language_code": lang,
            "speaker": config.SARVAM_TTS_SPEAKER,
            "model": config.SARVAM_TTS_MODEL,
            "speech_sample_rate": config.SAMPLE_RATE,
        },
    )
    _check(resp, "text-to-speech")
    wav_bytes = base64.b64decode(resp.json()["audios"][0])
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (config.SAMPLE_RATE, 1, 2):
            raise RuntimeError(f"Unexpected TTS audio format: {w.getparams()}")
        pcm = w.readframes(w.getnframes())
    log.info("text-to-speech (%s, %d chars) took %.2fs", lang, len(text), time.monotonic() - started)
    return pcm


def _task_for(text: str, lang: str) -> asyncio.Task:
    key = (lang, text)
    task = _tts_tasks.get(key)
    if task is None or task.cancelled() or (task.done() and task.exception() is not None):
        task = asyncio.create_task(_synthesize_uncached(text, lang))
        _tts_tasks[key] = task
        while len(_tts_tasks) > MAX_CACHED_AUDIOS:      # drop the oldest entry
            _tts_tasks.pop(next(iter(_tts_tasks)))
    return task


async def synthesize(text: str, lang: str) -> bytes:
    """Text -> 8 kHz 16-bit mono PCM. Instant if prefetch() already did the work."""
    return await asyncio.shield(_task_for(text, lang))


def _log_prefetch_failure(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is not None:
        log.warning("Audio prefetch failed (it will be retried when needed): %s", task.exception())


def prefetch(text: str, lang: str) -> None:
    """Start generating audio in the background. Never raises."""
    try:
        _task_for(text, lang).add_done_callback(_log_prefetch_failure)
    except Exception:
        log.exception("Could not start audio prefetch")