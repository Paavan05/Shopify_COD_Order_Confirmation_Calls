import asyncio
import json
import logging

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, WebSocket

from . import config, exotel, languages, messages, shopify, speech
from .session import CallSession

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("main")

app = FastAPI()

# call_sid -> order state. All attempts for one order share the same dict.
PENDING_CALLS: dict[str, dict] = {}
SEEN_ORDERS: set[int] = set()  # Shopify can deliver the same webhook twice
FAILED_STATUSES = {"no-answer", "busy", "failed", "canceled"}


async def place_call(order_state: dict):
    order_state["attempts"] += 1
    # Generate the greeting audio now, while the phone is ringing, so it is ready
    # the moment the customer answers.
    speech.prefetch(messages.build_greeting(order_state), order_state["language"])
    try:
        call_sid = await exotel.make_call(order_state["phone"])
    except Exception:
        # A problem on our side or Exotel's, not the customer's: never cancel for this.
        log.exception("Could not start call for order %s", order_state["id"])
        return
    PENDING_CALLS[call_sid] = order_state
    log.info("Call %s (attempt %s) started for order %s",
             call_sid, order_state["attempts"], order_state["id"])


async def handle_failed_attempt(order_state: dict, call_sid: str, reason: str):
    """Called when the customer did not pick up, or hung up before deciding."""
    if order_state["finished"] or call_sid in order_state["handled_calls"]:
        return
    order_state["handled_calls"].add(call_sid)
    log.info("Order %s attempt %s failed (%s)", order_state["id"], order_state["attempts"], reason)

    if order_state["attempts"] < config.MAX_CALL_ATTEMPTS:
        await asyncio.sleep(config.RETRY_DELAY_SECONDS)
        if not order_state["finished"]:
            await place_call(order_state)
    else:
        order_state["finished"] = True
        try:
            await shopify.cancel_order(order_state["id"])
            log.info("Order %s cancelled after %s failed attempts",
                     order_state["id"], order_state["attempts"])
        except Exception:
            log.exception("Could not cancel order %s", order_state["id"])


async def on_hangup(order_state: dict, call_sid: str, reason: str):
    # Run in the background so the finished WebSocket handler is not held open.
    asyncio.create_task(handle_failed_attempt(order_state, call_sid, reason))


async def start_confirmation_call(order: dict):
    phone = shopify.get_customer_phone(order)
    if not phone:
        log.warning("Order %s has no usable phone number", order["id"])
        return
    items = order.get("line_items", [])
    language = languages.detect_language(order)
    addr = order.get("shipping_address") or {}
    log.info("Order %s ships to %s (%s) -> language %s",
             order["id"], addr.get("province"), addr.get("province_code"), language)
    order_state = {
        "id": order["id"],
        "number": order.get("order_number") or order.get("name"),
        "total": int(float(order.get("total_price", "0"))),
        "product": (items[0].get("title") or "")[:60] if items else "",
        "extra_items": max(len(items) - 1, 0),
        "language": language,
        "phone": phone,
        "attempts": 0,
        "finished": False,
        "handled_calls": set(),
    }
    await place_call(order_state)


@app.post("/webhooks/shopify/orders-create")
async def orders_create(request: Request, background: BackgroundTasks):
    raw = await request.body()
    if not shopify.verify_hmac(raw, request.headers.get("X-Shopify-Hmac-Sha256", "")):
        raise HTTPException(status_code=401, detail="Bad signature")
    order = json.loads(raw)
    if not shopify.is_cod(order):
        return {"status": "ignored (not COD)"}
    if order["id"] in SEEN_ORDERS:
        return {"status": "duplicate"}
    SEEN_ORDERS.add(order["id"])
    background.add_task(start_confirmation_call, order)  # reply to Shopify fast
    return {"status": "accepted"}


@app.post("/exotel/call-status")
async def call_status(request: Request, background: BackgroundTasks):
    try:
        body = await request.json()
    except Exception:
        body = dict(await request.form())
    call_sid = body.get("CallSid")
    status = (body.get("Status") or "").lower()
    log.info("Exotel call status: %s -> %s", call_sid, status)
    order_state = PENDING_CALLS.get(call_sid)
    if order_state and status in FAILED_STATUSES:
        background.add_task(handle_failed_attempt, order_state, call_sid, status)
    return {"ok": True}


@app.websocket("/ws/voicebot")
async def voicebot(ws: WebSocket):
    await ws.accept()
    await CallSession(ws, PENDING_CALLS, on_hangup).run()