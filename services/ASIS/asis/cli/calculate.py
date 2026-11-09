"""
``asis calculate`` subcommand: deterministic local mathematics.

Runs the shared CalculatorEngine directly (no LLM needed): parses
flags into one structured engine call and prints the exact result,
decimal, and verification. Fully offline.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from asis.calculator.engine import OPERATIONS


def build_calculate_parser() -> argparse.ArgumentParser:
    """Build the ``asis calculate`` command-line parser."""
    parser = argparse.ArgumentParser(
        prog="asis calculate",
        description="A.S.I.S. offline calculator (local engine, no internet).",
    )
    parser.add_argument(
        "expression",
        nargs="?",
        default=None,
        help="expression to evaluate, e.g. 'sqrt(144)' or 'x^2 - 5*x + 6 = 0'",
    )
    parser.add_argument(
        "--expression",
        dest="expression_flag",
        default=None,
        help="expression to evaluate (alternative to the positional argument)",
    )
    parser.add_argument(
        "--operation",
        default="calculate",
        choices=sorted(OPERATIONS),
        help="engine operation (default: %(default)s)",
    )
    parser.add_argument("--equation", default=None, help="equation for solve/ode")
    parser.add_argument("--equations", default=None, help="';'-separated system")
    parser.add_argument("--variables", default=None, help="';'-separated variables")
    parser.add_argument("--variable", default=None, help="single variable")
    parser.add_argument("--function", default=None, help="named function")
    parser.add_argument("--arguments", default=None, help="';'-separated arguments")
    parser.add_argument("--value", default=None, help="plain value")
    parser.add_argument("--from", dest="from_unit", default=None, help="source unit")
    parser.add_argument("--to", dest="to_unit", default=None, help="target unit")
    parser.add_argument("--data", default=None, help="dataset '[1, 2, 3]'")
    parser.add_argument("--angle-mode", default=None, help="radians/degrees/gradians")
    parser.add_argument(
        "--param",
        dest="extra",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="extra operation parameter (repeatable)",
    )
    return parser


def _collect_params(args: argparse.Namespace) -> dict:
    params: dict[str, str] = {}
    expression = (
        args.expression_flag if args.expression_flag is not None else args.expression
    )
    if expression is not None:
        params["expression"] = expression
    for key in (
        "equation",
        "equations",
        "variables",
        "variable",
        "function",
        "arguments",
        "value",
        "data",
        "angle_mode",
    ):
        value = getattr(args, key)
        if value is not None:
            params[key] = value
    if args.from_unit is not None:
        params["from"] = args.from_unit
    if args.to_unit is not None:
        params["to"] = args.to_unit
    for item in args.extra or []:
        if "=" not in item:
            print(f"ignoring malformed --param '{item}' (expected KEY=VALUE)")
            continue
        key, _, value = item.partition("=")
        params[key.strip()] = value.strip()
    return params


def run_calculate(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``asis calculate``."""
    from asis.calculator.engine import build_engine_from_settings
    from asis.calculator.errors import CalculatorError

    args = build_calculate_parser().parse_args(argv)
    engine = build_engine_from_settings()
    try:
        result = engine.calculate(args.operation, _collect_params(args))
    except CalculatorError as exc:
        print(f"{exc.code}: {exc.message.split(': ', 1)[-1]}")
        return 2
    lines = []
    if result.exact_result is not None:
        lines.append(f"Exact: {result.exact_result}")
    if result.numeric_result is not None:
        lines.append(f"Decimal: {result.numeric_result}")
    if result.units:
        lines[-1] = f"{lines[-1]} {result.units}" if lines else f"Units: {result.units}"
    for step in result.steps:
        lines.append(step)
    if result.verification is not None:
        method = result.verification.get("method", "verification")
        match = result.verification.get("match")
        lines.append(f"Verified ({method}): {match}")
    for warning in result.warnings:
        lines.append(f"Warning: {warning}")
    print("\n".join(lines) if lines else "(no result)")
    return 0
