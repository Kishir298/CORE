"""
R.E.S.C.S. integration surface for A.S.I.S.
"""

from .adapter import RESCSAdapter
from .client import StorageClient, StoredRecord

__all__ = ["StorageClient", "StoredRecord", "RESCSAdapter"]
