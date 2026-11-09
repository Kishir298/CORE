"""Local document ingestion for the A.S.I.S. interactive terminal.

Offline-first: files are parsed locally into bounded normalized text.
No network, no tracking, no cloud processing.
"""

from .context import build_document_context
from .parsers import SUPPORTED_SUFFIXES, parse_file
from .store import AttachedDocument, DocumentStore

__all__ = [
    "SUPPORTED_SUFFIXES",
    "AttachedDocument",
    "DocumentStore",
    "build_document_context",
    "parse_file",
]
