import base64
import hashlib
import hmac
import re

import httpx

from . import config


def verify_hmac(raw_body: bytes, header_hmac: str) -> bool:
    digest = hmac.new(config.SHOPIFY_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), header_hmac)


def is_cod(order: dict) -> bool:
    names = [n.lower() for n in order.get("payment_gateway_names", [])]
    return any(k in n for n in names for k in config.COD_KEYWORDS)


def get_customer_phone(order: dict) -> str | None:
    candidates = [
        order.get("phone"),
        (order.get("shipping_address") or {}).get("phone"),
        (order.get("billing_address") or {}).get("phone"),
        (order.get("customer") or {}).get("phone"),
    ]
    for raw in candidates:
        if raw:
            digits = re.sub(r"\D", "", raw)
            if len(digits) >= 10:
                return "+91" + digits[-10:]  # assumes Indian numbers
    return None


async def _graphql(query: str, variables: dict) -> dict:
    url = f"https://{config.SHOPIFY_SHOP_DOMAIN}/admin/api/{config.SHOPIFY_API_VERSION}/graphql.json"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            url,
            headers={"X-Shopify-Access-Token": config.SHOPIFY_ACCESS_TOKEN},
            json={"query": query, "variables": variables},
        )
        resp.raise_for_status()
        body = resp.json()
    if body.get("errors"):
        raise RuntimeError(f"Shopify GraphQL errors: {body['errors']}")
    return body["data"]


def _gid(order_id: int | str) -> str:
    return f"gid://shopify/Order/{order_id}"


async def add_tag(order_id: int | str, tag: str) -> None:
    data = await _graphql(
        """mutation($id: ID!, $tags: [String!]!) {
             tagsAdd(id: $id, tags: $tags) { userErrors { field message } }
           }""",
        {"id": _gid(order_id), "tags": [tag]},
    )
    errs = data["tagsAdd"]["userErrors"]
    if errs:
        raise RuntimeError(f"tagsAdd failed: {errs}")


async def confirm_order(order_id: int | str) -> None:
    # Shopify has no "confirmed" status, so confirmation is recorded as a tag.
    await add_tag(order_id, "COD-Confirmed")


async def cancel_order(order_id: int | str) -> None:
    data = await _graphql(
        """mutation($orderId: ID!, $reason: OrderCancelReason!, $refund: Boolean!,
                    $restock: Boolean!, $notifyCustomer: Boolean) {
             orderCancel(orderId: $orderId, reason: $reason, refund: $refund,
                         restock: $restock, notifyCustomer: $notifyCustomer) {
               job { id }
               orderCancelUserErrors { field message code }
             }
           }""",
        {
            "orderId": _gid(order_id),
            "reason": "CUSTOMER",
            "refund": False,   # COD: nothing has been paid yet
            "restock": True,
            "notifyCustomer": False,
        },
    )
    errs = data["orderCancel"]["orderCancelUserErrors"]
    if errs:
        raise RuntimeError(f"orderCancel failed: {errs}")