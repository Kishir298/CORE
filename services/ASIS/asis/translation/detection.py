"""
Offline language detection for the A.S.I.S. Translation Engine.

Dependency-free and deterministic: Unicode script analysis combined
with stopword profiles for the major registry languages. No cloud API,
no web request, no model download.

Uncertain input (short text, close scores, unknown scripts) yields an
explicit uncertain result instead of an invented language.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

_STRIP_CATEGORIES = frozenset({"P", "N", "S", "Z", "C"})


def _tokens(text: str) -> list[str]:
    """Split on whitespace, stripping edge punctuation/symbols.

    Interior combining marks (e.g. Devanagari matras) are preserved, so
    Indic words stay intact — ``\\w``-based splitting would shred them.
    """
    out: list[str] = []
    for raw in text.split():
        start, end = 0, len(raw)
        while start < end and unicodedata.category(raw[start])[0] in _STRIP_CATEGORIES:
            start += 1
        while end > start and (
            unicodedata.category(raw[end - 1])[0] in _STRIP_CATEGORIES
        ):
            end -= 1
        token = raw[start:end].casefold()
        if token:
            out.append(token)
    return out


@dataclass(frozen=True)
class DetectionResult:
    """Outcome of offline language detection."""

    language: str | None  # canonical registry code, or None when unknown
    confidence: float  # 0.0 - 1.0
    uncertain: bool  # True when the guess must not be trusted blindly


def _script_of(char: str) -> str:
    point = ord(char)
    if 0x0900 <= point <= 0x097F:
        return "Deva"
    if 0x0600 <= point <= 0x06FF or 0x0750 <= point <= 0x077F:
        return "Arab"
    if 0x0400 <= point <= 0x04FF:
        return "Cyrl"
    if 0x4E00 <= point <= 0x9FFF or 0x3400 <= point <= 0x4DBF:
        return "Hani"
    if 0x3040 <= point <= 0x30FF:
        return "Jpan"
    if 0xAC00 <= point <= 0xD7AF or 0x1100 <= point <= 0x11FF:
        return "Kore"
    if 0x0E00 <= point <= 0x0E7F:
        return "Thai"
    if 0x1200 <= point <= 0x137F:
        return "Ethi"
    if 0x0370 <= point <= 0x03FF:
        return "Grek"
    if 0x0590 <= point <= 0x05FF:
        return "Hebr"
    if 0x0980 <= point <= 0x09FF:
        return "Beng"
    if 0x0B80 <= point <= 0x0BFF:
        return "Taml"
    if 0x0C00 <= point <= 0x0C7F:
        return "Telu"
    if 0x0D00 <= point <= 0x0D7F:
        return "Mlym"
    if 0x0C80 <= point <= 0x0CFF:
        return "Knda"
    if 0x0A80 <= point <= 0x0AFF:
        return "Gujr"
    if 0x0A00 <= point <= 0x0A7F:
        return "Guru"
    if 0x0D80 <= point <= 0x0DFF:
        return "Sinh"
    if 0x1000 <= point <= 0x109F:
        return "Mymr"
    if 0x1780 <= point <= 0x17FF:
        return "Khmr"
    if 0x0E80 <= point <= 0x0EFF:
        return "Laoo"
    if 0x0530 <= point <= 0x058F:
        return "Armn"
    if 0x10A0 <= point <= 0x10FF:
        return "Geor"
    if (
        0x0041 <= point <= 0x007A
        or 0x00C0 <= point <= 0x00FF
        or 0x0100 <= point <= 0x017F
    ):
        return "Latn"
    return "other"


# Stopword profiles: lowercase word -> weight-1 each. Kept small and
# curated; coverage beyond these languages falls back to script-level
# uncertainty rather than invention.
_STOPWORDS: dict[str, frozenset[str]] = {
    "en": frozenset(
            ["the", "be", "to", "of", "and", "a", "in", "that", "have", "it", "for",
            "not", "on", "with", "he", "as", "you", "do", "at", "this", "but", "his",
            "by", "from", "they", "we", "say", "her", "she", "or", "an", "will",
            "my", "one", "all", "would", "there", "their", "what", "so", "up", "out",
            "if", "about", "who", "get", "which", "go", "me", "when", "where", "is",
            "are", "was", "were", "has", "had", "hello", "thanks", "please"]
    ),
    "fr": frozenset(
            ["le", "la", "les", "de", "des", "du", "un", "une", "et", "est", "en",
            "dans", "que", "qui", "pour", "pas", "sur", "plus", "par", "avec", "ce",
            "cette", "son", "sa", "ses", "leur", "leurs", "nous", "vous", "ils",
            "elles", "où", "est", "sont", "avez", "bonjour", "merci", "oui", "non",
            "aeroport"]
    ),
    "de": frozenset(
            ["der", "die", "das", "und", "den", "dem", "ein", "eine", "ist", "im",
            "zu", "von", "mit", "sich", "auf", "für", "nicht", "aber", "auch", "als",
            "am", "an", "aus", "bei", "nach", "noch", "nur", "oder", "so", "vor",
            "zum", "danke", "bitte"]
    ),
    "es": frozenset(
            ["el", "la", "los", "las", "de", "del", "un", "una", "y", "en", "que",
            "es", "por", "para", "con", "no", "una", "su", "al", "como", "más",
            "pero", "sus", "entre", "cuando", "donde", "hola", "gracias"]
    ),
    "it": frozenset(
            ["il", "lo", "la", "i", "gli", "le", "di", "del", "della", "un", "una",
            "e", "in", "che", "è", "per", "con", "non", "una", "sono", "come",
            "dove", "quando", "grazie", "ciao"]
    ),
    "pt": frozenset(
            ["o", "a", "os", "as", "de", "do", "da", "dos", "das", "um", "uma", "e",
            "em", "que", "é", "para", "com", "não", "uma", "são", "como", "onde",
            "quando", "obrigado", "olá"]
    ),
    "nl": frozenset(
            ["de", "het", "een", "van", "en", "in", "op", "dat", "te", "die", "dit",
            "met", "voor", "niet", "er", "aan", "door", "over", "waar", "wanneer",
            "dank"]
    ),
    "hi": frozenset(
            ["है", "हैं", "का", "की", "के", "को", "ने", "से", "में", "पर", "और",
            "यह", "वह", "जो", "तो", "भी", "नहीं", "क्या", "कहाँ", "कैसे", "आप", "हम",
            "तुम", "मैं", "है।", "नमस्ते", "धन्यवाद"]
    ),
    "ar": frozenset(
            ["من", "في", "على", "إلى", "أن", "لا", "ما", "هذا", "هذه", "التي",
            "الذي", "كان", "مع", "عن", "عند", "بين", "أين", "كيف", "شكرا", "مرحبا",
            "هل"]
    ),
    "fa": frozenset(
            ["از", "در", "به", "که", "را", "با", "برای", "این", "آن", "است", "هست",
            "نیست", "چه", "کجا", "ممنون", "سلام"]
    ),
    "ur": frozenset(
            ["کا", "کی", "کے", "کو", "نے", "سے", "میں", "پر", "اور", "یہ", "وہ",
            "جو", "تو", "بھی", "نہیں", "کیا", "کہاں", "کیسے", "آپ", "ہم", "تم",
            "میں", "شکریہ"]
    ),
    "ru": frozenset(
            ["и", "в", "не", "на", "с", "что", "как", "это", "по", "из", "за", "от",
            "для", "до", "при", "или", "но", "если", "где", "когда", "спасибо",
            "здравствуйте"]
    ),
    "uk": frozenset(
            ["і", "в", "не", "на", "з", "що", "як", "це", "по", "із", "за", "від",
            "для", "до", "при", "або", "але", "якщо", "де", "коли", "дякую"]
    ),
    "bn": frozenset(
            ["এর", "একটি", "মধ্যে", "থেকে", "করে", "জন্য", "এই", "সেই", "আর", "না",
            "কি", "কোথায়", "কেমন", "ধন্যবাদ"]
    ),
    "tr": frozenset(
            ["bir", "ve", "de", "da", "bu", "şu", "için", "gibi", "çok", "ne",
            "nasıl", "nerede", "teşekkür", "merhaba"]
    ),
    "pl": frozenset(
            ["i", "w", "nie", "na", "z", "do", "się", "że", "to", "jak", "jest",
            "są", "gdzie", "kiedy", "dziękuję"]
    ),
}

# Dominant-script shortcut for scripts essentially unique to one registry
# language (still requires a minimum share of the text).
_SCRIPT_LANGUAGE: dict[str, str] = {
    "Thai": "th",
    "Khmr": "km",
    "Laoo": "lo",
    "Mymr": "my",
    "Sinh": "si",
    "Grek": "el",
    "Armn": "hy",
    "Geor": "ka",
    "Hebr": "he",
    "Jpan": "ja",
    "Kore": "ko",
    "Taml": "ta",
    "Telu": "te",
    "Mlym": "ml",
    "Knda": "kn",
    "Gujr": "gu",
    "Guru": "pa",
}

_MIN_TOKENS_CONFIDENT = 3
_MIN_SCORE_CONFIDENT = 0.18
_MIN_MARGIN_CONFIDENT = 0.06
_MIN_SCRIPT_SHARE = 0.5


def detect_language(text: str) -> DetectionResult:
    """Detect the registry language of ``text`` offline.

    Returns a confident result only when script + stopword evidence is
    strong; otherwise returns the best guess (or None) with
    ``uncertain=True``.
    """
    if not isinstance(text, str) or not text.strip():
        return DetectionResult(language=None, confidence=0.0, uncertain=True)
    cleaned = text.strip()
    if len(cleaned) > 10_000:
        cleaned = cleaned[:10_000]

    letters = [ch for ch in cleaned if ch.isalpha()]
    if not letters:
        return DetectionResult(language=None, confidence=0.0, uncertain=True)

    script_counts: dict[str, int] = {}
    for char in letters:
        script = _script_of(char)
        script_counts[script] = script_counts.get(script, 0) + 1
    dominant, dominant_count = max(
        script_counts.items(), key=lambda item: item[1]
    )
    script_share = dominant_count / len(letters)

    tokens = _tokens(cleaned)
    scores: dict[str, float] = {}
    if tokens:
        for code, words in _STOPWORDS.items():
            hits = sum(1 for token in tokens if token in words)
            if hits:
                scores[code] = hits / len(tokens)

    # Script-unique languages short-circuit when the script dominates.
    if dominant in _SCRIPT_LANGUAGE and script_share >= _MIN_SCRIPT_SHARE:
        code = _SCRIPT_LANGUAGE[dominant]
        boost = scores.get(code, 0.0)
        confidence = min(0.95, 0.55 + script_share * 0.3 + boost)
        uncertain = len(tokens) < _MIN_TOKENS_CONFIDENT
        return DetectionResult(
            language=code, confidence=confidence, uncertain=uncertain
        )

    if not scores:
        return DetectionResult(language=None, confidence=0.0, uncertain=True)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_code, best_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = best_score - runner_up

    confident = (
        len(tokens) >= _MIN_TOKENS_CONFIDENT
        and best_score >= _MIN_SCORE_CONFIDENT
        and margin >= _MIN_MARGIN_CONFIDENT
    )
    confidence = min(0.95, best_score + (0.1 if margin >= 0.15 else 0.0))
    return DetectionResult(
        language=best_code, confidence=confidence, uncertain=not confident
    )
