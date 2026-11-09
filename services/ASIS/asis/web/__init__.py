"""
A.S.I.S. basic web access provider layer.

Sole network boundary for ``web_search``/``web_fetch``. Independent of
CORE, A.S.C.S., voice, and Ollama-specific code.
"""

from asis.web.provider import (
    DuckDuckGoWebProvider,
    WebProvider,
    WebProviderError,
    build_default_provider,
    parse_ddg_results,
)

__all__ = [
    "DuckDuckGoWebProvider",
    "WebProvider",
    "WebProviderError",
    "build_default_provider",
    "parse_ddg_results",
]
