"""
Unit system with dimensional validation.

Factors relative to SI base units per dimension; temperature uses
affine conversion separately. Cross-dimension conversions are rejected
(``5 kg → m``) instead of silently producing nonsense.
"""

from __future__ import annotations

from asis.calculator import errors
from asis.calculator.parser import parse_number

# unit -> (dimension, factor to SI base, offset applied before scaling)
_UNITS: dict[str, tuple[str, float, float]] = {
    # length (m)
    "m": ("length", 1.0, 0.0),
    "meter": ("length", 1.0, 0.0),
    "meters": ("length", 1.0, 0.0),
    "km": ("length", 1000.0, 0.0),
    "cm": ("length", 0.01, 0.0),
    "mm": ("length", 0.001, 0.0),
    "mi": ("length", 1609.344, 0.0),
    "mile": ("length", 1609.344, 0.0),
    "miles": ("length", 1609.344, 0.0),
    "ft": ("length", 0.3048, 0.0),
    "foot": ("length", 0.3048, 0.0),
    "feet": ("length", 0.3048, 0.0),
    "in": ("length", 0.0254, 0.0),
    "inch": ("length", 0.0254, 0.0),
    "inches": ("length", 0.0254, 0.0),
    "yd": ("length", 0.9144, 0.0),
    "yard": ("length", 0.9144, 0.0),
    "nmi": ("length", 1852.0, 0.0),
    # mass (kg)
    "kg": ("mass", 1.0, 0.0),
    "g": ("mass", 0.001, 0.0),
    "mg": ("mass", 1e-6, 0.0),
    "lb": ("mass", 0.45359237, 0.0),
    "lbs": ("mass", 0.45359237, 0.0),
    "pound": ("mass", 0.45359237, 0.0),
    "oz": ("mass", 0.028349523125, 0.0),
    "t": ("mass", 1000.0, 0.0),
    # time (s)
    "s": ("time", 1.0, 0.0),
    "sec": ("time", 1.0, 0.0),
    "min": ("time", 60.0, 0.0),
    "h": ("time", 3600.0, 0.0),
    "hr": ("time", 3600.0, 0.0),
    "day": ("time", 86400.0, 0.0),
    "ms": ("time", 0.001, 0.0),
    "us": ("time", 1e-6, 0.0),
    # temperature (K, affine). Canonical names avoid clashing with
    # coulomb (C) and farad (F); use degC/degF/degR or the aliases.
    "K": ("temperature", 1.0, 0.0),
    "degC": ("temperature", 1.0, 273.15),
    "degF": ("temperature", 5.0 / 9.0, 459.67),
    "degR": ("temperature", 5.0 / 9.0, 0.0),
    # area (m^2)
    "m2": ("area", 1.0, 0.0),
    "km2": ("area", 1e6, 0.0),
    "cm2": ("area", 1e-4, 0.0),
    "ft2": ("area", 0.09290304, 0.0),
    "acre": ("area", 4046.8564224, 0.0),
    "ha": ("area", 10000.0, 0.0),
    # volume (m^3)
    "m3": ("volume", 1.0, 0.0),
    "L": ("volume", 0.001, 0.0),
    "l": ("volume", 0.001, 0.0),
    "mL": ("volume", 1e-6, 0.0),
    "gal": ("volume", 0.003785411784, 0.0),
    "qt": ("volume", 0.000946352946, 0.0),
    "floz": ("volume", 2.95735295625e-5, 0.0),
    # speed (m/s)
    "mps": ("speed", 1.0, 0.0),
    "kph": ("speed", 1000.0 / 3600.0, 0.0),
    "mph": ("speed", 1609.344 / 3600.0, 0.0),
    "knot": ("speed", 1852.0 / 3600.0, 0.0),
    # acceleration (m/s^2)
    "mps2": ("acceleration", 1.0, 0.0),
    # force (N)
    "N": ("force", 1.0, 0.0),
    "lbf": ("force", 4.4482216152605, 0.0),
    "dyn": ("force", 1e-5, 0.0),
    # pressure (Pa)
    "Pa": ("pressure", 1.0, 0.0),
    "kPa": ("pressure", 1000.0, 0.0),
    "MPa": ("pressure", 1e6, 0.0),
    "bar": ("pressure", 1e5, 0.0),
    "psi": ("pressure", 6894.757293168, 0.0),
    "atm": ("pressure", 101325.0, 0.0),
    "mmHg": ("pressure", 133.322387415, 0.0),
    # energy (J)
    "J": ("energy", 1.0, 0.0),
    "kJ": ("energy", 1000.0, 0.0),
    "cal": ("energy", 4.184, 0.0),
    "kcal": ("energy", 4184.0, 0.0),
    "eV": ("energy", 1.602176634e-19, 0.0),
    "Wh": ("energy", 3600.0, 0.0),
    "kWh": ("energy", 3.6e6, 0.0),
    "BTU": ("energy", 1055.05585262, 0.0),
    # power (W)
    "W": ("power", 1.0, 0.0),
    "kW": ("power", 1000.0, 0.0),
    "MW": ("power", 1e6, 0.0),
    "hp": ("power", 745.69987158227022, 0.0),
    # frequency (Hz)
    "Hz": ("frequency", 1.0, 0.0),
    "kHz": ("frequency", 1000.0, 0.0),
    "MHz": ("frequency", 1e6, 0.0),
    "GHz": ("frequency", 1e9, 0.0),
    # charge (C)
    "C": ("charge", 1.0, 0.0),
    "mC": ("charge", 0.001, 0.0),
    "uC": ("charge", 1e-6, 0.0),
    "Ah": ("charge", 3600.0, 0.0),
    # voltage (V)
    "V": ("voltage", 1.0, 0.0),
    "mV": ("voltage", 0.001, 0.0),
    "kV": ("voltage", 1000.0, 0.0),
    # current (A)
    "A": ("current", 1.0, 0.0),
    "mA": ("current", 0.001, 0.0),
    # resistance (ohm)
    "ohm": ("resistance", 1.0, 0.0),
    "kohm": ("resistance", 1000.0, 0.0),
    "Mohm": ("resistance", 1e6, 0.0),
    # capacitance (F)
    "F": ("capacitance", 1.0, 0.0),
    "mF": ("capacitance", 0.001, 0.0),
    "uF": ("capacitance", 1e-6, 0.0),
    "nF": ("capacitance", 1e-9, 0.0),
    "pF": ("capacitance", 1e-12, 0.0),
    # inductance (H)
    "H": ("inductance", 1.0, 0.0),
    "mH": ("inductance", 0.001, 0.0),
    "uH": ("inductance", 1e-6, 0.0),
    # angle (rad)
    "rad": ("angle", 1.0, 0.0),
    "deg": ("angle", 0.017453292519943295, 0.0),
    "grad": ("angle", 0.015707963267948967, 0.0),
    "rev": ("angle", 6.283185307179586, 0.0),
}

_ALIASES = {
    "celsius": "degC",
    "Celsius": "degC",
    "°C": "degC",
    "℃": "degC",
    "fahrenheit": "degF",
    "Fahrenheit": "degF",
    "°F": "degF",
    "℉": "degF",
    "rankine": "degR",
    "kelvin": "K",
    "meters": "m",
    "kilometers": "km",
    "miles": "mi",
    "kilograms": "kg",
    "grams": "g",
    "pounds": "lb",
    "seconds": "s",
    "minutes": "min",
    "hours": "h",
    "newton": "N",
    "newtons": "N",
    "joule": "J",
    "joules": "J",
    "watt": "W",
    "watts": "W",
    "volt": "V",
    "volts": "V",
    "ampere": "A",
    "amperes": "A",
    "amp": "A",
    "amps": "A",
    "degrees": "deg",
    "degree": "deg",
    "radians": "rad",
    "hertz": "Hz",
    "pascal": "Pa",
    "pascals": "Pa",
}


def normalize_unit(name: str) -> str:
    """Resolve aliases and validate a unit name."""
    key = (name or "").strip()
    if not key:
        raise errors.invalid_expression("unit must be a non-empty string")
    if key in _ALIASES:
        return _ALIASES[key]
    if key in _UNITS:
        return key
    raise errors.invalid_expression(f"unknown unit '{name}'")


def to_si(value: float, unit: str) -> tuple[float, str]:
    """Convert to SI base; temperature affine handled correctly."""
    code = normalize_unit(unit)
    dimension, factor, offset = _UNITS[code]
    if dimension == "temperature":
        if code == "degF":
            return (value + offset) * factor, dimension
        return value * factor + offset, dimension
    return value * factor, dimension


def from_si(si_value: float, unit: str) -> float:
    """Convert from SI base to ``unit``."""
    code = normalize_unit(unit)
    dimension, factor, offset = _UNITS[code]
    if dimension == "temperature":
        if code == "degF":
            return si_value / factor - offset
        return (si_value - offset) / factor
    return si_value / factor


def convert(value_text: str, from_unit: str, to_unit: str) -> dict:
    """Convert a value between units with dimensional validation."""
    try:
        value = parse_number(value_text)
    except errors.CalculatorError:
        raise errors.invalid_expression("conversion value must be numeric") from None
    source = normalize_unit(from_unit)
    target = normalize_unit(to_unit)
    source_dim = _UNITS[source][0]
    if source_dim != _UNITS[target][0]:
        raise errors.dimension_error(
            f"cannot convert {source_dim} ({source}) to {_UNITS[target][0]} ({target})"
        )
    si_value, _ = to_si(value, source)
    result = from_si(si_value, target)
    return {
        "value": value,
        "from": source,
        "result": result,
        "to": target,
        "dimension": source_dim,
    }


def list_units(dimension: str | None = None) -> list[str]:
    """List known units, optionally filtered by dimension."""
    if dimension is None:
        return sorted(_UNITS)
    wanted = dimension.strip().lower()
    return sorted(name for name, (dim, _, _) in _UNITS.items() if dim == wanted)
