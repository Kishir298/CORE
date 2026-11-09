"""
A.S.I.S. offline calculator: deterministic local mathematics.

SymPy-backed symbolic/numeric engine behind a safe parser — no eval,
no network, no model. The engine is the source of truth; the LLM only
translates natural language into structured calculator requests.
"""

from asis.calculator.engine import (
    OPERATIONS,
    CalculatorEngine,
    build_engine_from_settings,
)
from asis.calculator.errors import CalculatorError
from asis.calculator.models import CalculatorResult

__all__ = [
    "CalculatorEngine",
    "OPERATIONS",
    "build_engine_from_settings",
    "CalculatorError",
    "CalculatorResult",
]
