"""Pick the call language from the order's shipping address."""

DEFAULT_LANGUAGE = "hi-IN"   # Indian address, but state missing or not in the table below
INTERNATIONAL_LANGUAGE = "en-IN"  # shipping address outside India

SUPPORTED_LANGUAGES = {
    "hi-IN", "bn-IN", "ta-IN", "te-IN", "gu-IN", "kn-IN",
    "ml-IN", "mr-IN", "pa-IN", "od-IN", "en-IN",
}

# Shopify province codes for India -> language. States not listed use DEFAULT_LANGUAGE.
STATE_CODE_TO_LANGUAGE = {
    "GJ": "gu-IN",                  # Gujarat
    "MH": "mr-IN",                  # Maharashtra
    "WB": "bn-IN",                  # West Bengal
    "TN": "ta-IN",                  # Tamil Nadu
    "AP": "te-IN",                  # Andhra Pradesh
    "TS": "te-IN", "TG": "te-IN",   # Telangana (Shopify uses TS, ISO uses TG)
    "KA": "kn-IN",                  # Karnataka
    "KL": "ml-IN",                  # Kerala
    "PB": "pa-IN",                  # Punjab
    "OD": "od-IN", "OR": "od-IN",   # Odisha (older code: OR)
}

# Fallback when the province code is missing: match on the state name.
STATE_NAME_TO_LANGUAGE = {
    "gujarat": "gu-IN",
    "maharashtra": "mr-IN",
    "west bengal": "bn-IN",
    "tamil nadu": "ta-IN",
    "andhra pradesh": "te-IN",
    "telangana": "te-IN",
    "karnataka": "kn-IN",
    "kerala": "ml-IN",
    "punjab": "pa-IN",
    "odisha": "od-IN",
    "orissa": "od-IN",
}


def detect_language(order: dict) -> str:
    addr = order.get("shipping_address") or {}

    # 1. Shipping address outside India -> English
    country_code = (addr.get("country_code") or "").strip().upper()
    country_name = (addr.get("country") or "").strip().lower()
    if country_code:
        if country_code != "IN":
            return INTERNATIONAL_LANGUAGE
    elif country_name and country_name != "india":
        return INTERNATIONAL_LANGUAGE

    # 2. India: use the state's language; missing or unmapped state -> Hindi
    code = (addr.get("province_code") or "").strip().upper()
    if code in STATE_CODE_TO_LANGUAGE:
        return STATE_CODE_TO_LANGUAGE[code]
    name = (addr.get("province") or "").strip().lower()
    return STATE_NAME_TO_LANGUAGE.get(name, DEFAULT_LANGUAGE)