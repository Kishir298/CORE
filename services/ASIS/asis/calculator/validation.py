"""
Input validation and resource limits for the calculator.

Every user-supplied string passes through here before parsing or
evaluation: length caps, banned-token scan (code-execution surface),
and structural budgets (matrix size, dataset size, polynomial degree).
"""

from __future__ import annotations

from asis.calculator import errors

# Substrings that always indicate a code-execution attempt, never
# legitimate mathematics. Checked case-insensitively on the raw input.
BANNED_TOKENS = (
    "__",
    "import",
    "exec",
    "eval",
    "open(",
    "compile",
    "getattr",
    "setattr",
    "globals",
    "locals",
    "vars(",
    "os.",
    "sys.",
    "subprocess",
    "system(",
    "popen",
    "input(",
    "breakpoint",
    "lambda",
    "yield",
    "await",
    "class ",
    "def ",
    "del ",
    "global ",
    "nonlocal ",
    "assert ",
    "raise ",
    "try:",
    "except",
    "finally",
    "with ",
    "for ",
    "while ",
    "print(",
    "help(",
    "dir(",
    "id(",
    "repr(",
    "chr(",
    "ord(",
    "bytes",
    "bytearray",
    "memoryview",
    "object",
    "type(",
    "super(",
    "property",
    "staticmethod",
    "classmethod",
    "mro(",
    "subclasses",
    "func_",
    "im_",
    "gi_",
    "cr_",
    "tb_",
)

DEFAULT_MAX_EXPRESSION_CHARS = 2_000
DEFAULT_MAX_MATRIX_SIZE = 10
DEFAULT_MAX_DATASET_SIZE = 10_000
DEFAULT_MAX_POLY_DEGREE = 20


def check_expression(
    text: str, *, max_chars: int = DEFAULT_MAX_EXPRESSION_CHARS
) -> str:
    """Validate raw input; return the stripped text or raise."""
    if not isinstance(text, str) or not text.strip():
        raise errors.invalid_expression("expression must be a non-empty string")
    cleaned = text.strip()
    if len(cleaned) > max_chars:
        raise errors.too_large(max_chars)
    lowered = cleaned.lower()
    for token in BANNED_TOKENS:
        if token in lowered:
            raise errors.invalid_expression(
                "expression contains constructs outside mathematics"
            )
    return cleaned


def check_matrix_shape(
    rows: int, cols: int, *, max_size: int = DEFAULT_MAX_MATRIX_SIZE
) -> None:
    """Validate matrix dimensions before any operation."""
    if rows <= 0 or cols <= 0:
        raise errors.dimension_error("matrix dimensions must be positive")
    if rows > max_size or cols > max_size:
        raise errors.too_complex(
            f"matrix {rows}x{cols} exceeds the {max_size}x{max_size} limit"
        )


def check_dataset_size(size: int, *, max_size: int = DEFAULT_MAX_DATASET_SIZE) -> None:
    """Validate dataset length before statistics."""
    if size <= 0:
        raise errors.domain_error("dataset must not be empty")
    if size > max_size:
        raise errors.too_complex(
            f"dataset of {size} values exceeds the {max_size} limit"
        )


def check_poly_degree(
    degree: int, *, max_degree: int = DEFAULT_MAX_POLY_DEGREE
) -> None:
    """Validate polynomial degree before symbolic solving."""
    if degree < 0:
        raise errors.domain_error("invalid polynomial degree")
    if degree > max_degree:
        raise errors.too_complex(
            f"polynomial degree {degree} exceeds the {max_degree} limit"
        )
