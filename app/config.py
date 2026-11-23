import os
from dotenv import load_dotenv

load_dotenv()


def _req(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


# Public address of this server (used for Exotel's call-status callback)
PUBLIC_BASE_URL = _req("PUBLIC_BASE_URL").rstrip("/")

# Shopify
SHOPIFY_SHOP_DOMAIN = _req("SHOPIFY_SHOP_DOMAIN")
SHOPIFY_ACCESS_TOKEN = _req("SHOPIFY_ACCESS_TOKEN")
SHOPIFY_WEBHOOK_SECRET = _req("SHOPIFY_WEBHOOK_SECRET")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-07")
STORE_NAME = os.getenv("STORE_NAME", "our store")
COD_KEYWORDS = ("cod", "cash on delivery")  # matched against payment gateway names

# Exotel
EXOTEL_ACCOUNT_SID = _req("EXOTEL_ACCOUNT_SID")
EXOTEL_API_KEY = _req("EXOTEL_API_KEY")
EXOTEL_API_TOKEN = _req("EXOTEL_API_TOKEN")
EXOTEL_SUBDOMAIN = os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.com")
EXOTEL_EXOPHONE = _req("EXOTEL_EXOPHONE")
EXOTEL_FLOW_APP_ID = _req("EXOTEL_FLOW_APP_ID")

# Sarvam
SARVAM_API_KEY = _req("SARVAM_API_KEY")
SARVAM_TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
SARVAM_TTS_SPEAKER = os.getenv("SARVAM_TTS_SPEAKER", "priya")

# Call attempts
MAX_CALL_ATTEMPTS = 2        # first call + one retry (no answer, or hang-up before deciding)
RETRY_DELAY_SECONDS = 60     # wait before calling again

# Conversation rules
MAX_REPEATS = 1              # question is repeated once; still unclear -> order is cancelled
SAMPLE_RATE = 8000           # telephony audio: 8 kHz, 16-bit mono PCM
SPEECH_RMS_THRESHOLD = 500   # loudness above this counts as speech (tune this)
SILENCE_END_SECONDS = 0.9    # this much silence ends the customer's utterance
NO_SPEECH_TIMEOUT = 7.0      # no speech for this long counts as an unclear answer
MAX_UTTERANCE_SECONDS = 8.0
MIN_UTTERANCE_SECONDS = 0.25