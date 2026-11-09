"""A.S.I.S. persistent identity reconstruction + simulation subsystem.

Real system: parsers, pipeline, storage, retrieval, modes, persona,
calibration, questions, CLI. No mega-prompt. See docs/identity.md.
"""

from .matching import MatchResult, match_identity
from .model import IdentityRecord, MemoryClass, Provenance
from .whatsapp import WhatsAppMessage, parse_whatsapp_export

__all__ = [
    "IdentityRecord",
    "Provenance",
    "MemoryClass",
    "WhatsAppMessage",
    "parse_whatsapp_export",
    "match_identity",
    "MatchResult",
]
