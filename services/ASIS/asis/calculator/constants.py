"""
Mathematical and physical constants.

Values from CODATA 2022 / NIST where applicable; definitions note the
unit and source. Pure data — no computation, no network.
"""

from __future__ import annotations

MATH_CONSTANTS: dict[str, dict[str, str]] = {
    "pi": {"value": "pi", "description": "circle constant, circumference/diameter"},
    "e": {"value": "E", "description": "Euler's number, base of natural logarithms"},
    "tau": {"value": "2*pi", "description": "circle constant, circumference/radius"},
    "phi": {
        "value": "(1 + sqrt(5))/2",
        "description": "golden ratio",
    },
    "i": {"value": "I", "description": "imaginary unit, sqrt(-1)"},
}

# value, unit, source note.
PHYSICAL_CONSTANTS: dict[str, dict[str, str]] = {
    "c": {
        "value": "299792458",
        "unit": "m/s",
        "description": "speed of light in vacuum (exact, SI defining)",
    },
    "G": {
        "value": "6.67430e-11",
        "unit": "m^3 kg^-1 s^-2",
        "description": "Newtonian constant of gravitation (CODATA 2022)",
    },
    "h": {
        "value": "6.62607015e-34",
        "unit": "J s",
        "description": "Planck constant (exact, SI defining)",
    },
    "hbar": {
        "value": "1.054571817e-34",
        "unit": "J s",
        "description": "reduced Planck constant (CODATA 2022)",
    },
    "kB": {
        "value": "1.380649e-23",
        "unit": "J/K",
        "description": "Boltzmann constant (exact, SI defining)",
    },
    "e_charge": {
        "value": "1.602176634e-19",
        "unit": "C",
        "description": "elementary charge (exact, SI defining)",
    },
    "m_e": {
        "value": "9.1093837015e-31",
        "unit": "kg",
        "description": "electron mass (CODATA 2022)",
    },
    "m_p": {
        "value": "1.67262192595e-27",
        "unit": "kg",
        "description": "proton mass (CODATA 2022)",
    },
    "N_A": {
        "value": "6.02214076e23",
        "unit": "mol^-1",
        "description": "Avogadro constant (exact, SI defining)",
    },
    "R": {
        "value": "8.314462618",
        "unit": "J mol^-1 K^-1",
        "description": "molar gas constant (CODATA 2022)",
    },
    "epsilon_0": {
        "value": "8.8541878188e-12",
        "unit": "F/m",
        "description": "vacuum electric permittivity (CODATA 2022)",
    },
    "mu_0": {
        "value": "1.25663706127e-6",
        "unit": "N/A^2",
        "description": "vacuum magnetic permeability (CODATA 2022)",
    },
    "g": {
        "value": "9.80665",
        "unit": "m/s^2",
        "description": "standard acceleration of gravity (exact, conventional)",
    },
}


def constant_value(name: str) -> tuple[str, str | None, str]:
    """Return (value expression, unit or None, description) for ``name``."""
    from asis.calculator import errors

    key = (name or "").strip()
    if key in MATH_CONSTANTS:
        entry = MATH_CONSTANTS[key]
        return entry["value"], None, entry["description"]
    if key in PHYSICAL_CONSTANTS:
        entry = PHYSICAL_CONSTANTS[key]
        return entry["value"], entry["unit"], entry["description"]
    raise errors.invalid_expression(f"unknown constant '{name}'")
