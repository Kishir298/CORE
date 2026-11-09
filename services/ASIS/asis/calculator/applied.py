"""
Applied mathematics: physics, engineering, and finance formulas.

Pure closed-form functions over validated numeric inputs with units
recorded per result. Engineering stays calculation-only (no control
instructions). Finance is pure math with stated assumptions (no bank,
account, or market connectivity of any kind).
"""

from __future__ import annotations

import math

from asis.calculator import errors
from asis.calculator.parser import parse_number


def _num(name: str, raw: str) -> float:
    try:
        return parse_number(raw)
    except errors.CalculatorError:
        raise errors.invalid_expression(f"'{name}' must be numeric") from None


def _positive(name: str, raw: str, *, allow_zero: bool = False) -> float:
    value = _num(name, raw)
    if value < 0 or (value == 0 and not allow_zero):
        raise errors.domain_error(f"'{name}' must be positive")
    return value


def physics(formula: str, params: dict[str, str]) -> dict:
    """Evaluate a named physics formula; units recorded on the result."""
    name = (formula or "").strip().lower()

    def get(key, positive=False):
        if positive:
            return _positive(key, params.get(key, ""))
        return _num(key, params.get(key, ""))

    if name in ("velocity", "speed"):
        distance, time = get("distance", positive=True), get("time", positive=True)
        if time == 0:
            raise errors.domain_error("time must be nonzero")
        return {"result": distance / time, "unit": "m/s", "formula": "v = d / t"}
    if name == "acceleration":
        dv = get("delta_v")
        time = get("time", positive=True)
        if time == 0:
            raise errors.domain_error("time must be nonzero")
        return {"result": dv / time, "unit": "m/s^2", "formula": "a = Δv / t"}
    if name == "displacement":
        initial_v, time, acc = get("v0"), get("t", positive=True), get("a")
        return {
            "result": initial_v * time + 0.5 * acc * time**2,
            "unit": "m",
            "formula": "s = v0·t + ½·a·t²",
        }
    if name == "force":
        mass, acc = get("mass", positive=True), get("a")
        return {"result": mass * acc, "unit": "N", "formula": "F = m·a"}
    if name == "momentum":
        return {
            "result": get("mass", positive=True) * get("v"),
            "unit": "kg·m/s",
            "formula": "p = m·v",
        }
    if name == "kinetic_energy":
        mass, vel = get("mass", positive=True), get("v")
        return {"result": 0.5 * mass * vel**2, "unit": "J", "formula": "KE = ½·m·v²"}
    if name == "potential_energy":
        mass, height = get("mass", positive=True), get("h", positive=True)
        gravity = get("g") if params.get("g", "").strip() else 9.80665
        return {"result": mass * gravity * height, "unit": "J", "formula": "PE = m·g·h"}
    if name == "work":
        force, distance = get("force"), get("distance", positive=True)
        return {"result": force * distance, "unit": "J", "formula": "W = F·d"}
    if name == "power":
        work, time = get("work"), get("time", positive=True)
        if time == 0:
            raise errors.domain_error("time must be nonzero")
        return {"result": work / time, "unit": "W", "formula": "P = W / t"}
    if name == "ohms_law":
        keys = {k for k in ("V", "I", "R") if params.get(k, "").strip()}
        if len(keys) != 2:
            raise errors.invalid_expression("ohms_law needs exactly two of V, I, R")
        if keys == {"V", "I"}:
            current = get("I")
            if current == 0:
                raise errors.domain_error("current must be nonzero")
            return {"result": get("V") / current, "unit": "ohm", "formula": "R = V / I"}
        if keys == {"V", "R"}:
            resistance = get("R")
            if resistance == 0:
                raise errors.domain_error("resistance must be nonzero")
            return {
                "result": get("V") / resistance,
                "unit": "A",
                "formula": "I = V / R",
            }
        return {"result": get("I") * get("R"), "unit": "V", "formula": "V = I·R"}
    if name == "electrical_power":
        keys = {k for k in ("V", "I", "R", "P") if params.get(k, "").strip()}
        if len(keys) < 2:
            raise errors.invalid_expression("electrical_power needs two of V, I, R, P")
        vals = {k: get(k) for k in keys}
        if "V" in vals and "I" in vals:
            return {"result": vals["V"] * vals["I"], "unit": "W", "formula": "P = V·I"}
        if "I" in vals and "R" in vals:
            return {
                "result": vals["I"] ** 2 * vals["R"],
                "unit": "W",
                "formula": "P = I²·R",
            }
        if "V" in vals and "R" in vals:
            if vals["R"] == 0:
                raise errors.domain_error("resistance must be nonzero")
            return {
                "result": vals["V"] ** 2 / vals["R"],
                "unit": "W",
                "formula": "P = V²/R",
            }
        raise errors.invalid_expression("electrical_power needs a computable pair")
    if name == "wave_speed":
        return {
            "result": get("frequency", positive=True)
            * get("wavelength", positive=True),
            "unit": "m/s",
            "formula": "v = f·λ",
        }
    if name == "wavelength":
        freq = get("frequency", positive=True)
        if freq == 0:
            raise errors.domain_error("frequency must be nonzero")
        speed = (
            get("speed", positive=True)
            if params.get("speed", "").strip()
            else 299792458.0
        )
        return {"result": speed / freq, "unit": "m", "formula": "λ = v / f"}
    if name == "period":
        freq = get("frequency", positive=True)
        if freq == 0:
            raise errors.domain_error("frequency must be nonzero")
        return {"result": 1 / freq, "unit": "s", "formula": "T = 1 / f"}
    if name == "heat":
        return {
            "result": get("mass", positive=True)
            * get("c", positive=True)
            * get("delta_T"),
            "unit": "J",
            "formula": "Q = m·c·ΔT",
        }
    raise errors.invalid_expression(f"unknown physics formula '{formula}'")


def engineering(calculation: str, params: dict[str, str]) -> dict:
    """Practical engineering calculations (math only, no control)."""
    name = (calculation or "").strip().lower()

    def get(key, positive=False):
        if positive:
            return _positive(key, params.get(key, ""))
        return _num(key, params.get(key, ""))

    if name == "series_resistance":
        values = [
            _num(f"R{i}", raw) for i, raw in enumerate(params.values()) if raw.strip()
        ]
        if not values:
            raise errors.invalid_expression("series_resistance needs resistor values")
        if any(v < 0 for v in values):
            raise errors.domain_error("resistances must be non-negative")
        return {"result": math.fsum(values), "unit": "ohm", "formula": "Rs = ΣR"}
    if name == "parallel_resistance":
        values = [
            _num(f"R{i}", raw) for i, raw in enumerate(params.values()) if raw.strip()
        ]
        if not values:
            raise errors.invalid_expression("parallel_resistance needs resistor values")
        if any(v <= 0 for v in values):
            raise errors.domain_error("resistances must be positive")
        return {
            "result": 1 / math.fsum(1 / v for v in values),
            "unit": "ohm",
            "formula": "1/Rp = Σ(1/R)",
        }
    if name == "voltage_divider":
        vin, r1, r2 = get("Vin"), get("R1", positive=True), get("R2", positive=True)
        return {
            "result": vin * r2 / (r1 + r2),
            "unit": "V",
            "formula": "Vout = Vin·R2/(R1+R2)",
        }
    if name == "torque":
        return {
            "result": get("force") * get("radius", positive=True),
            "unit": "N·m",
            "formula": "τ = F·r",
        }
    if name == "mechanical_power":
        return {
            "result": get("torque") * get("omega"),
            "unit": "W",
            "formula": "P = τ·ω",
        }
    if name == "efficiency":
        out, inp = get("out"), get("in")
        if inp == 0:
            raise errors.domain_error("input must be nonzero")
        return {"result": out / inp * 100, "unit": "%", "formula": "η = out/in·100%"}
    if name == "stress":
        area = get("area", positive=True)
        if area == 0:
            raise errors.domain_error("area must be nonzero")
        return {"result": get("force") / area, "unit": "Pa", "formula": "σ = F/A"}
    if name == "strain":
        length = get("length", positive=True)
        if length == 0:
            raise errors.domain_error("length must be nonzero")
        return {"result": get("delta_L") / length, "unit": "", "formula": "ε = ΔL/L"}
    raise errors.invalid_expression(f"unknown engineering calculation '{calculation}'")


def finance(calculation: str, params: dict[str, str]) -> dict:
    """Pure-mathematics finance (assumptions stated, no connectivity)."""
    name = (calculation or "").strip().lower()

    def get(key):
        return _num(key, params.get(key, ""))

    if name == "simple_interest":
        principal, rate, time = get("P"), get("r"), get("t")
        return {
            "result": principal * rate * time,
            "formula": "I = P·r·t",
            "assumptions": "simple interest, rate as decimal per period",
        }
    if name == "compound_future_value":
        principal, rate = get("P"), get("r")
        compounds = int(get("n")) if params.get("n", "").strip() else 1
        time = get("t")
        if compounds <= 0:
            raise errors.domain_error("compounding periods must be positive")
        return {
            "result": principal * (1 + rate / compounds) ** (compounds * time),
            "formula": "FV = P·(1+r/n)^(n·t)",
            "assumptions": "fixed rate, rate as decimal",
        }
    if name == "present_value":
        future, rate, time = get("FV"), get("r"), get("t")
        return {
            "result": future / (1 + rate) ** time,
            "formula": "PV = FV/(1+r)^t",
            "assumptions": "fixed discount rate as decimal",
        }
    if name == "loan_payment":
        principal, rate = get("P"), get("r")
        periods = int(get("n"))
        if periods <= 0:
            raise errors.domain_error("periods must be positive")
        if rate == 0:
            payment = principal / periods
        else:
            payment = principal * rate / (1 - (1 + rate) ** -periods)
        return {
            "result": payment,
            "formula": "PMT = P·r/(1-(1+r)^-n)",
            "assumptions": (
                "fixed rate per period, rate as decimal, end-of-period payments"
            ),
        }
    if name == "cagr":
        start, end = get("start"), get("end")
        periods = get("periods")
        if start <= 0 or periods <= 0:
            raise errors.domain_error("start and periods must be positive")
        return {
            "result": (end / start) ** (1 / periods) - 1,
            "formula": "CAGR = (end/start)^(1/n) - 1",
            "assumptions": "result as decimal; multiply by 100 for percent",
        }
    if name == "percent_change":
        old, new = get("old"), get("new")
        if old == 0:
            raise errors.domain_error("old value must be nonzero")
        return {
            "result": (new - old) / abs(old) * 100,
            "unit": "%",
            "formula": "(new-old)/|old|·100%",
        }
    if name == "straight_line_depreciation":
        cost, salvage, life = get("cost"), get("salvage"), get("life")
        if life <= 0:
            raise errors.domain_error("life must be positive")
        return {
            "result": (cost - salvage) / life,
            "formula": "(cost-salvage)/life",
            "assumptions": "straight-line, per-period amount",
        }
    raise errors.invalid_expression(f"unknown finance calculation '{calculation}'")
