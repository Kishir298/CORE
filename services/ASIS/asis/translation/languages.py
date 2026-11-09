"""
Canonical language registry for the A.S.I.S. Translation Engine.

Authoritative source for language identity used by translation,
detection, tools, CLI, voice, and validation. Entries reflect the
MADLAD-400 supported language set (Apache-2.0 model); text translation
is supported for every entry, while speech input/output flags are
conservative, documented capability claims (see module notes).

Speech capability basis (documented, host-dependent):
- ``supported_for_speech_input``: languages broadly covered by the
  local faster-whisper STT backend.
- ``supported_for_speech_output``: major languages for which desktop OS
  TTS voices commonly exist. The actual host voice inventory decides at
  speak time; absence raises ``TTS_LANGUAGE_UNSUPPORTED``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    """A single translatable language."""

    code: str  # BCP-47 primary subtag, lowercase (e.g. "en", "hi")
    name: str  # English display name
    native_name: str  # Endonym in its own script
    script: str  # ISO 15924 script code (e.g. "Latn", "Deva", "Arab")
    supported_for_text: bool = True
    supported_for_speech_input: bool = False
    supported_for_speech_output: bool = False

    @property
    def madlad_tag(self) -> str:
        """Control token used by MADLAD-400 MT (``<2xx>`` convention)."""
        return f"<2{TAG_OVERRIDES.get(self.code, self.code)}>"


# MADLAD-400 control-token overrides where the model tag differs from the
# registry code. Curated from the MADLAD-400 convention; operators adding
# models verify tags against the model card.
TAG_OVERRIDES: dict[str, str] = {
    "nb": "no",  # Norwegian Bokmal under the "no" tag
}


def _lang(
    code: str,
    name: str,
    native: str,
    script: str,
    speech_in: bool = False,
    speech_out: bool = False,
) -> Language:
    return Language(
        code=code,
        name=name,
        native_name=native,
        script=script,
        supported_for_text=True,
        supported_for_speech_input=speech_in,
        supported_for_speech_output=speech_out,
    )


LANGUAGES: tuple[Language, ...] = (
    # World majors (text + speech in/out commonly available).
    _lang("en", "English", "English", "Latn", True, True),
    _lang("hi", "Hindi", "हिन्दी", "Deva", True, True),
    _lang("fr", "French", "français", "Latn", True, True),
    _lang("ar", "Arabic", "العربية", "Arab", True, True),
    _lang("es", "Spanish", "español", "Latn", True, True),
    _lang("de", "German", "Deutsch", "Latn", True, True),
    _lang("it", "Italian", "italiano", "Latn", True, True),
    _lang("pt", "Portuguese", "português", "Latn", True, True),
    _lang("ru", "Russian", "русский", "Cyrl", True, True),
    _lang("zh", "Chinese", "中文", "Hans", True, True),
    _lang("ja", "Japanese", "日本語", "Jpan", True, True),
    _lang("ko", "Korean", "한국어", "Kore", True, True),
    _lang("nl", "Dutch", "Nederlands", "Latn", True, True),
    _lang("pl", "Polish", "polski", "Latn", True, True),
    _lang("tr", "Turkish", "Türkçe", "Latn", True, True),
    _lang("uk", "Ukrainian", "українська", "Cyrl", True, False),
    _lang("fa", "Persian", "فارسی", "Arab", True, False),
    _lang("ur", "Urdu", "اردو", "Arab", True, False),
    _lang("bn", "Bengali", "বাংলা", "Beng", True, False),
    _lang("ta", "Tamil", "தமிழ்", "Taml", True, False),
    _lang("te", "Telugu", "తెలుగు", "Telu", True, False),
    _lang("ml", "Malayalam", "മലയാളം", "Mlym", True, False),
    _lang("id", "Indonesian", "Bahasa Indonesia", "Latn", True, True),
    _lang("ms", "Malay", "Bahasa Melayu", "Latn", True, False),
    _lang("vi", "Vietnamese", "Tiếng Việt", "Latn", True, False),
    _lang("th", "Thai", "ไทย", "Thai", True, False),
    # Europe.
    _lang("cs", "Czech", "čeština", "Latn", True, False),
    _lang("sk", "Slovak", "slovenčina", "Latn", True, False),
    _lang("sl", "Slovenian", "slovenščina", "Latn", True, False),
    _lang("hr", "Croatian", "hrvatski", "Latn", True, False),
    _lang("sr", "Serbian", "српски", "Cyrl", True, False),
    _lang("bs", "Bosnian", "bosanski", "Latn", True, False),
    _lang("bg", "Bulgarian", "български", "Cyrl", True, False),
    _lang("ro", "Romanian", "română", "Latn", True, False),
    _lang("hu", "Hungarian", "magyar", "Latn", True, False),
    _lang("el", "Greek", "Ελληνικά", "Grek", True, False),
    _lang("da", "Danish", "dansk", "Latn", True, False),
    _lang("sv", "Swedish", "svenska", "Latn", True, False),
    _lang("no", "Norwegian", "norsk", "Latn", True, False),
    _lang("nb", "Norwegian Bokmål", "norsk bokmål", "Latn", False, False),
    _lang("fi", "Finnish", "suomi", "Latn", True, False),
    _lang("is", "Icelandic", "íslenska", "Latn", True, False),
    _lang("et", "Estonian", "eesti", "Latn", True, False),
    _lang("lv", "Latvian", "latviešu", "Latn", True, False),
    _lang("lt", "Lithuanian", "lietuvių", "Latn", True, False),
    _lang("ca", "Catalan", "català", "Latn", True, False),
    _lang("gl", "Galician", "galego", "Latn", True, False),
    _lang("eu", "Basque", "euskara", "Latn", True, False),
    _lang("mt", "Maltese", "Malti", "Latn", True, False),
    _lang("cy", "Welsh", "Cymraeg", "Latn", True, False),
    _lang("ga", "Irish", "Gaeilge", "Latn", False, False),
    _lang("sq", "Albanian", "shqip", "Latn", True, False),
    _lang("mk", "Macedonian", "македонски", "Cyrl", True, False),
    _lang("be", "Belarusian", "беларуская", "Cyrl", True, False),
    _lang("hy", "Armenian", "հայերեն", "Armn", True, False),
    _lang("ka", "Georgian", "ქართული", "Geor", True, False),
    _lang("he", "Hebrew", "עברית", "Hebr", True, False),
    _lang("yi", "Yiddish", "ייִדיש", "Hebr", True, False),
    _lang("af", "Afrikaans", "Afrikaans", "Latn", True, False),
    _lang("eo", "Esperanto", "Esperanto", "Latn", False, False),
    _lang("la", "Latin", "Latina", "Latn", False, False),
    # Middle East / Central Asia.
    _lang("az", "Azerbaijani", "azərbaycanca", "Latn", True, False),
    _lang("kk", "Kazakh", "қазақша", "Cyrl", True, False),
    _lang("ky", "Kyrgyz", "кыргызча", "Cyrl", False, False),
    _lang("uz", "Uzbek", "oʻzbekcha", "Latn", False, False),
    _lang("tk", "Turkmen", "Türkmençe", "Latn", False, False),
    _lang("ku", "Kurdish", "kurdî", "Latn", False, False),
    _lang("ps", "Pashto", "پښتو", "Arab", False, False),
    _lang("ug", "Uyghur", "ئۇيغۇرچە", "Arab", False, False),
    _lang("tg", "Tajik", "тоҷикӣ", "Cyrl", False, False),
    _lang("mn", "Mongolian", "монгол", "Cyrl", True, False),
    # South Asia.
    _lang("kn", "Kannada", "ಕನ್ನಡ", "Knda", True, False),
    _lang("mr", "Marathi", "मराठी", "Deva", True, False),
    _lang("gu", "Gujarati", "ગુજરાતી", "Gujr", True, False),
    _lang("pa", "Punjabi", "ਪੰਜਾਬੀ", "Guru", True, False),
    _lang("or", "Odia", "ଓଡ଼ିଆ", "Orya", False, False),
    _lang("as", "Assamese", "অসমীয়া", "Beng", False, False),
    _lang("ne", "Nepali", "नेपाली", "Deva", True, False),
    _lang("si", "Sinhala", "සිංහල", "Sinh", True, False),
    _lang("ks", "Kashmiri", "کٲشُر", "Arab", False, False),
    _lang("sd", "Sindhi", "سنڌي", "Arab", False, False),
    _lang("mai", "Maithili", "मैथिली", "Deva", False, False),
    _lang("sa", "Sanskrit", "संस्कृतम्", "Deva", False, False),
    _lang("brx", "Bodo", "बड़ो", "Deva", False, False),
    _lang("doi", "Dogri", "डोगरी", "Deva", False, False),
    _lang("kok", "Konkani", "कोंकणी", "Deva", False, False),
    _lang("mni", "Manipuri", "মণিপুরী", "Beng", False, False),
    _lang("sat", "Santali", "ᱥᱟᱱᱛᱟᱲᱤ", "Olck", False, False),
    # East / Southeast Asia.
    _lang("yue", "Cantonese", "粵語", "Hant", False, False),
    _lang("km", "Khmer", "ខ្មែរ", "Khmr", True, False),
    _lang("lo", "Lao", "ລາວ", "Laoo", True, False),
    _lang("my", "Burmese", "မြန်မာ", "Mymr", True, False),
    _lang("tl", "Tagalog", "Tagalog", "Latn", True, False),
    _lang("ceb", "Cebuano", "Bisaya", "Latn", False, False),
    _lang("jv", "Javanese", "Basa Jawa", "Latn", True, False),
    _lang("su", "Sundanese", "Basa Sunda", "Latn", False, False),
    _lang("hmn", "Hmong", "Hmoob", "Latn", False, False),
    _lang("mi", "Māori", "te reo Māori", "Latn", False, False),
    # Africa.
    _lang("sw", "Swahili", "Kiswahili", "Latn", True, False),
    _lang("am", "Amharic", "አማርኛ", "Ethi", True, False),
    _lang("ha", "Hausa", "Hausa", "Latn", True, False),
    _lang("yo", "Yoruba", "Yorùbá", "Latn", True, False),
    _lang("ig", "Igbo", "Igbo", "Latn", True, False),
    _lang("zu", "Zulu", "isiZulu", "Latn", True, False),
    _lang("xh", "Xhosa", "isiXhosa", "Latn", True, False),
    _lang("so", "Somali", "Soomaali", "Latn", True, False),
    _lang("ti", "Tigrinya", "ትግርኛ", "Ethi", False, False),
    _lang("sn", "Shona", "chiShona", "Latn", False, False),
    _lang("rw", "Kinyarwanda", "Ikinyarwanda", "Latn", False, False),
    _lang("mg", "Malagasy", "Malagasy", "Latn", False, False),
    _lang("ny", "Chichewa", "Chichewa", "Latn", False, False),
    _lang("st", "Sesotho", "Sesotho", "Latn", False, False),
    _lang("tn", "Tswana", "Setswana", "Latn", False, False),
    _lang("ts", "Tsonga", "Xitsonga", "Latn", False, False),
    _lang("ve", "Venda", "Tshivenda", "Latn", False, False),
    _lang("ss", "Swati", "siSwati", "Latn", False, False),
    _lang("nr", "Southern Ndebele", "isiNdebele", "Latn", False, False),
    _lang("nd", "Northern Ndebele", "isiNdebele", "Latn", False, False),
    _lang("lg", "Ganda", "Luganda", "Latn", False, False),
    _lang("ak", "Akan", "Akan", "Latn", False, False),
    _lang("ee", "Ewe", "Eʋegbe", "Latn", False, False),
    _lang("fon", "Fon", "Fon", "Latn", False, False),
    _lang("wo", "Wolof", "Wolof", "Latn", False, False),
    _lang("bm", "Bambara", "Bamanankan", "Latn", False, False),
    _lang("ff", "Fula", "Fulfulde", "Latn", False, False),
    _lang("kri", "Krio", "Krio", "Latn", False, False),
    # Americas / Pacific.
    _lang("qu", "Quechua", "Runa Simi", "Latn", False, False),
    _lang("gn", "Guarani", "Avañeʼẽ", "Latn", False, False),
    _lang("ay", "Aymara", "Aymar aru", "Latn", False, False),
    _lang("iu", "Inuktitut", "ᐃᓄᒃᑎᑐᑦ", "Cans", False, False),
    _lang("kl", "Greenlandic", "Kalaallisut", "Latn", False, False),
    _lang("haw", "Hawaiian", "ʻŌlelo Hawaiʻi", "Latn", False, False),
    _lang("tah", "Tahitian", "Reo Tahiti", "Latn", False, False),
    _lang("smo", "Samoan", "Gagana Samoa", "Latn", False, False),
    _lang("ton", "Tongan", "Lea faka-Tonga", "Latn", False, False),
    _lang("fij", "Fijian", "Na Vosa Vakaviti", "Latn", False, False),
)

_BY_CODE: dict[str, Language] = {lang.code: lang for lang in LANGUAGES}


def get_language(code: str) -> Language | None:
    """Look up a language by code (case-insensitive, whitespace-tolerant)."""
    if not isinstance(code, str):
        return None
    return _BY_CODE.get(code.strip().lower())


def normalize_code(code: str) -> str | None:
    """Return the canonical code for ``code``, or None when unsupported."""
    lang = get_language(code)
    return lang.code if lang is not None else None


def is_supported(code: str) -> bool:
    """Return True when ``code`` names a text-translatable language."""
    lang = get_language(code)
    return lang is not None and lang.supported_for_text


def supported_languages() -> list[Language]:
    """Return all text-translatable languages in registry order."""
    return [lang for lang in LANGUAGES if lang.supported_for_text]


def is_speech_input_supported(code: str) -> bool:
    """Return True when speech input is claimed for ``code``."""
    lang = get_language(code)
    return lang is not None and lang.supported_for_speech_input


def is_speech_output_supported(code: str) -> bool:
    """Return True when speech output is claimed for ``code``."""
    lang = get_language(code)
    return lang is not None and lang.supported_for_speech_output
