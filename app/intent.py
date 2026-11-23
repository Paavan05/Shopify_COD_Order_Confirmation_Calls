"""Decide whether a transcript means yes, no, or something unclear, in any supported language."""
import re

# Unambiguous words accepted in every language (many people mix in Hindi/English).
COMMON_YES = {
    "हां", "हाँ", "कन्फर्म", "कंफर्म", "ठीक", "haan", "han", "yes", "yeah", "ok", "okay", "confirm",
}
COMMON_NO = {
    "नहीं", "नही", "कैंसल", "केंसल", "nahi", "nahin", "no", "cancel",
}

LANG_YES = {
    "hi-IN": {"हांजी", "हाँजी", "बिल्कुल", "बिलकुल", "सही", "ओके", "theek", "bilkul"},
    "gu-IN": {"હા", "હાજી", "બરાબર", "ઠીક", "ઓકે", "કન્ફર્મ"},
    "mr-IN": {"होय", "हो", "बरोबर", "ठीक", "ओके", "कन्फर्म"},
    "bn-IN": {"হ্যাঁ", "হ্যা", "হাঁ", "ঠিক", "কনফার্ম", "ওকে", "জি"},
    "ta-IN": {"ஆம்", "ஆமா", "ஆமாம்", "சரி", "உறுதி", "கன்ஃபார்ம்", "ஓகே"},
    "te-IN": {"అవును", "ఔను", "సరే", "కన్ఫర్మ్", "ఓకే"},
    "kn-IN": {"ಹೌದು", "ಸರಿ", "ಕನ್ಫರ್ಮ್", "ಓಕೆ", "ಆಯ್ತು"},
    "ml-IN": {"അതെ", "ശരി", "കൺഫേം", "ഓക്കെ", "ആണ്"},
    "pa-IN": {"ਹਾਂ", "ਹਾਂਜੀ", "ਠੀਕ", "ਕਨਫਰਮ", "ਓਕੇ"},
    "od-IN": {"ହଁ", "ହାଁ", "ଠିକ୍", "ଠିକ", "କନଫର୍ମ", "ଓକେ"},
    "en-IN": {"sure", "correct", "right"},
}
LANG_NO = {
    "hi-IN": {"ना", "नो", "मत", "रद्द", "na", "mat"},
    "gu-IN": {"ના", "નથી", "નહિ", "રદ", "કેન્સલ", "નહીં"},
    "mr-IN": {"नाही", "नको", "रद्द", "रद्", "कॅन्सल"},
    "bn-IN": {"না", "নাহ", "বাতিল", "ক্যানসেল", "ক্যান্সেল"},
    "ta-IN": {"இல்லை", "இல்ல", "வேண்டாம்", "ரத்து", "கேன்சல்"},
    "te-IN": {"కాదు", "వద్దు", "లేదు", "రద్దు", "క్యాన్సల్"},
    "kn-IN": {"ಇಲ್ಲ", "ಬೇಡ", "ರದ್ದು", "ಕ್ಯಾನ್ಸಲ್"},
    "ml-IN": {"അല്ല", "വേണ്ട", "ഇല്ല", "റദ്ദ്", "ക്യാൻസൽ"},
    "pa-IN": {"ਨਹੀਂ", "ਨਾ", "ਰੱਦ", "ਕੈਂਸਲ"},
    "od-IN": {"ନା", "ନାହିଁ", "ବାତିଲ୍", "ବାତିଲ", "କ୍ୟାନ୍ସଲ"},
    "en-IN": {"don't", "dont", "not"},
}


def _tokens(text: str) -> list[str]:
    text = text.lower().replace("ँ", "ं")  # हाँ -> हां
    # Split on whitespace/punctuation only. (\w would break Indic vowel signs.)
    return re.findall(r"[^\s,.!?।॥\"'\-]+", text)


def classify(text: str, lang: str = "hi-IN") -> str:
    """Return 'yes', 'no' or 'unclear'. Mixed signals are 'unclear' on purpose."""
    tokens = set(_tokens(text))
    yes_words = COMMON_YES | LANG_YES.get(lang, set())
    no_words = COMMON_NO | LANG_NO.get(lang, set())
    has_yes = bool(tokens & yes_words)
    has_no = bool(tokens & no_words)
    if has_yes and not has_no:
        return "yes"
    if has_no and not has_yes:
        return "no"
    return "unclear"