import logging

import httpx

from . import config

log = logging.getLogger("exotel")


async def make_call(to_number: str) -> str:
    """Start an outbound call to the customer. When they pick up, Exotel runs
    your flow (which contains the Voicebot applet). Returns the call SID.
    When the call ends, Exotel posts its final status to /exotel/call-status."""
    url = (
        f"https://{config.EXOTEL_SUBDOMAIN}/v1/Accounts/"
        f"{config.EXOTEL_ACCOUNT_SID}/Calls/connect.json"
    )
    data = {
        "From": to_number,
        "CallerId": config.EXOTEL_EXOPHONE,
        "Url": f"http://my.exotel.com/{config.EXOTEL_ACCOUNT_SID}/exoml/start_voice/{config.EXOTEL_FLOW_APP_ID}",
        "StatusCallback": f"{config.PUBLIC_BASE_URL}/exotel/call-status",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, data=data, auth=(config.EXOTEL_API_KEY, config.EXOTEL_API_TOKEN))
        if resp.status_code >= 400:
            log.error("Exotel error %s: %s", resp.status_code, resp.text)
        resp.raise_for_status()
        return resp.json()["Call"]["Sid"]