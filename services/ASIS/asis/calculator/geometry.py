"""
2D/3D geometry and triangle solving.

Closed-form formulas over validated numeric inputs. Ambiguous triangle
cases (SSA) report every valid solution instead of silently picking one.
"""

from __future__ import annotations

import math

from asis.calculator import errors
from asis.calculator.parser import parse_number


def _num(name: str, value: str, *, positive: bool = False) -> float:
    try:
        number = parse_number(value)
    except errors.CalculatorError:
        raise errors.invalid_expression(f"'{name}' must be numeric") from None
    if positive and number <= 0:
        raise errors.domain_error(f"'{name}' must be positive")
    return number


def _area2d(shape: str, params: dict[str, str]) -> dict:
    def get(name, positive=True):
        return _num(name, params.get(name, ""), positive=positive)

    if shape == "square":
        side = get("side")
        return {"perimeter": 4 * side, "area": side**2}
    if shape == "rectangle":
        length, width = get("length"), get("width")
        return {"perimeter": 2 * (length + width), "area": length * width}
    if shape == "triangle":
        if "base" in params and "height" in params:
            base, height = get("base"), get("height")
            return {"area": base * height / 2}
        sides = [params.get(k, "") for k in ("a", "b", "c")]
        if all(sides):
            a, b, c = (get(k, positive=True) for k in ("a", "b", "c"))
            if a + b <= c or a + c <= b or b + c <= a:
                raise errors.domain_error("sides violate the triangle inequality")
            semi = (a + b + c) / 2
            area = math.sqrt(semi * (semi - a) * (semi - b) * (semi - c))
            return {"perimeter": a + b + c, "area": area}
        raise errors.invalid_expression("triangle needs base+height or sides a,b,c")
    if shape == "circle":
        radius = get("radius")
        return {"circumference": 2 * math.pi * radius, "area": math.pi * radius**2}
    if shape == "ellipse":
        major, minor = get("a"), get("b")
        perimeter = math.pi * (
            3 * (major + minor) - math.sqrt((3 * major + minor) * (major + 3 * minor))
        )
        return {"perimeter": perimeter, "area": math.pi * major * minor}
    if shape == "parallelogram":
        base, side, height = get("base"), get("side"), get("height")
        return {"perimeter": 2 * (base + side), "area": base * height}
    if shape == "trapezoid":
        a, b, height = get("a"), get("b"), get("height")
        c, d = get("c"), get("d")
        return {"perimeter": a + b + c + d, "area": (a + b) / 2 * height}
    if shape == "polygon":
        sides = int(get("sides", positive=True))
        length = get("length")
        if sides < 3:
            raise errors.domain_error("polygons need at least 3 sides")
        perimeter = sides * length
        area = sides * length**2 / (4 * math.tan(math.pi / sides))
        return {"perimeter": perimeter, "area": area}
    raise errors.invalid_expression(f"unknown 2D shape '{shape}'")


def _volume3d(shape: str, params: dict[str, str]) -> dict:
    def get(name):
        return _num(name, params.get(name, ""), positive=True)

    if shape == "cube":
        side = get("side")
        return {"surface_area": 6 * side**2, "volume": side**3}
    if shape == "cuboid":
        length, width, height = get("length"), get("width"), get("height")
        return {
            "surface_area": 2 * (length * width + length * height + width * height),
            "volume": length * width * height,
        }
    if shape == "sphere":
        radius = get("radius")
        return {
            "surface_area": 4 * math.pi * radius**2,
            "volume": 4 / 3 * math.pi * radius**3,
        }
    if shape == "cylinder":
        radius, height = get("radius"), get("height")
        return {
            "surface_area": 2 * math.pi * radius * (radius + height),
            "volume": math.pi * radius**2 * height,
        }
    if shape == "cone":
        radius, height = get("radius"), get("height")
        slant = math.sqrt(radius**2 + height**2)
        return {
            "surface_area": math.pi * radius * (radius + slant),
            "volume": math.pi * radius**2 * height / 3,
        }
    if shape == "prism":
        base_area, perimeter, length = get("base_area"), get("perimeter"), get("length")
        return {
            "surface_area": 2 * base_area + perimeter * length,
            "volume": base_area * length,
        }
    if shape == "pyramid":
        base_area, perimeter, slant = get("base_area"), get("perimeter"), get("slant")
        height = get("height")
        return {
            "surface_area": base_area + perimeter * slant / 2,
            "volume": base_area * height / 3,
        }
    raise errors.invalid_expression(f"unknown 3D shape '{shape}'")


def geometry(shape: str, params: dict[str, str]) -> dict:
    """Compute perimeter/area or surface-area/volume for a named shape."""
    name = (shape or "").strip().lower()
    if name in (
        "square",
        "rectangle",
        "triangle",
        "circle",
        "ellipse",
        "parallelogram",
        "trapezoid",
        "polygon",
    ):
        return {"shape": name, **_area2d(name, params)}
    if name in ("cube", "cuboid", "sphere", "cylinder", "cone", "prism", "pyramid"):
        return {"shape": name, **_volume3d(name, params)}
    raise errors.invalid_expression(f"unknown shape '{shape}'")


def _deg(radians: float) -> float:
    return math.degrees(radians)


def triangle_solve(params: dict[str, str]) -> dict:
    """Solve a triangle from known sides/angles.

    Accepts any of SSS, SAS, ASA/AAS, RHS, SSA. The ambiguous SSA case
    returns every valid solution explicitly.
    """
    known: dict[str, float] = {}
    for key in ("a", "b", "c", "A", "B", "C"):
        raw = (params.get(key, "") or "").strip()
        if raw:
            try:
                known[key] = parse_number(raw)
            except errors.CalculatorError:
                raise errors.invalid_expression(f"'{key}' must be numeric") from None
    sides = {k for k in ("a", "b", "c") if k in known}
    angles = {k for k in ("A", "B", "C") if k in known}
    for key in angles:
        if not 0 < known[key] < 180:
            raise errors.domain_error("angles must be between 0 and 180 degrees")

    def _finish(a: float, b: float, c: float) -> dict:
        if min(a, b, c) <= 0 or a + b <= c or a + c <= b or b + c <= a:
            raise errors.domain_error("solution violates the triangle inequality")
        angle_a = _deg(math.acos((b * b + c * c - a * a) / (2 * b * c)))
        angle_b = _deg(math.acos((a * a + c * c - b * b) / (2 * a * c)))
        semi = (a + b + c) / 2
        return {
            "a": a,
            "b": b,
            "c": c,
            "A": angle_a,
            "B": angle_b,
            "C": 180 - angle_a - angle_b,
            "area": math.sqrt(semi * (semi - a) * (semi - b) * (semi - c)),
        }

    # SSS
    if sides == {"a", "b", "c"}:
        return {"solutions": [_finish(known["a"], known["b"], known["c"])]}
    # SAS / RHS
    sas_map = {
        frozenset(("a", "b", "C")): ("a", "b", "C"),
        frozenset(("a", "c", "B")): ("a", "c", "B"),
        frozenset(("b", "c", "A")): ("b", "c", "A"),
    }
    key = frozenset(known)
    if key in sas_map:
        s1, s2, ang = sas_map[key]
        opposite = {"A": "a", "B": "b", "C": "c"}[ang]
        side1, side2 = known[s1], known[s2]
        included = math.radians(known[ang])
        missing = math.sqrt(
            side1**2 + side2**2 - 2 * side1 * side2 * math.cos(included)
        )
        vals = {s1: side1, s2: side2, opposite: missing}
        return {"solutions": [_finish(vals["a"], vals["b"], vals["c"])]}
    # ASA / AAS: two angles + any side.
    if len(angles) == 2 and len(sides) == 1:
        angle_names = sorted(angles)
        missing_angle = ({"A", "B", "C"} - angles).pop()
        angle_sum = sum(known[a] for a in angles)
        if angle_sum >= 180:
            raise errors.domain_error("angle sum must be below 180 degrees")
        angles_full = {**known, missing_angle: 180 - angle_sum}
        side_name = next(iter(sides))
        side_len = known[side_name]
        angle_of_side = {"a": "A", "b": "B", "c": "C"}[side_name]
        ratio = side_len / math.sin(math.radians(angles_full[angle_of_side]))
        vals = {
            "a": ratio * math.sin(math.radians(angles_full["A"])),
            "b": ratio * math.sin(math.radians(angles_full["B"])),
            "c": ratio * math.sin(math.radians(angles_full["C"])),
        }
        return {"solutions": [_finish(vals["a"], vals["b"], vals["c"])]}
    # SSA (ambiguous): known side-angle pair + one more side.
    pairs = [("a", "A"), ("b", "B"), ("c", "C")]
    known_pairs = [(s, a) for s, a in pairs if s in known and a in known]
    lone_sides = [
        s
        for s in ("a", "b", "c")
        if s in known and s not in {p[0] for p in known_pairs}
    ]
    if len(known_pairs) == 1 and len(lone_sides) == 1 and len(known) == 3:
        side_known, angle_known = known_pairs[0]
        other_side = lone_sides[0]
        side_len = known[side_known]
        angle_rad = math.radians(known[angle_known])
        other_len = known[other_side]
        sin_other_angle = other_len * math.sin(angle_rad) / side_len
        if abs(sin_other_angle) > 1:
            raise errors.no_solution("SSA inputs admit no triangle")
        base = math.degrees(math.asin(max(-1.0, min(1.0, sin_other_angle))))
        candidates = [base] if abs(abs(base) - 90) < 1e-9 else [base, 180 - base]
        solutions = []
        third = ({"a", "b", "c"} - {side_known, other_side}).pop()
        angle_of = {"a": "A", "b": "B", "C": "C", "c": "C"}
        for candidate in candidates:
            total = known[angle_known] + candidate
            if total >= 180:
                continue
            third_angle = 180 - total
            ratio = side_len / math.sin(angle_rad)
            vals = {side_known: side_len, other_side: other_len}
            angle_names = {angle_known: known[angle_known]}
            other_angle_name = angle_of[other_side]
            angle_names[other_angle_name] = candidate
            third_angle_name = ({"A", "B", "C"} - set(angle_names)).pop()
            angle_names[third_angle_name] = third_angle
            vals[third] = ratio * math.sin(math.radians(third_angle))
            try:
                solutions.append(_finish(vals["a"], vals["b"], vals["c"]))
            except errors.CalculatorError:
                continue
        if not solutions:
            raise errors.no_solution("SSA inputs admit no triangle")
        out = {"solutions": solutions}
        if len(solutions) > 1:
            out["ambiguous"] = True
        return out
    raise errors.invalid_expression("triangle needs SSS, SAS, ASA/AAS, or SSA inputs")


def pythagoras(*, a: str = "", b: str = "", c: str = "") -> dict:
    """Solve a right triangle hypotenuse/leg (exactly one missing)."""
    missing = [name for name, raw in (("a", a), ("b", b), ("c", c)) if not raw.strip()]
    if len(missing) != 1:
        raise errors.invalid_expression("pythagoras needs exactly one missing side")
    try:
        sides = {
            name: parse_number(raw)
            for name, raw in (("a", a), ("b", b), ("c", c))
            if raw.strip()
        }
    except errors.CalculatorError:
        raise errors.invalid_expression("sides must be numeric") from None
    if any(v <= 0 for v in sides.values()):
        raise errors.domain_error("sides must be positive")
    which = missing[0]
    if which == "c":
        return {"c": math.sqrt(sides["a"] ** 2 + sides["b"] ** 2)}
    leg, hyp = sides["a" if which == "b" else "b"], sides["c"]
    if hyp <= leg:
        raise errors.domain_error("hypotenuse must exceed the known leg")
    return {which: math.sqrt(hyp**2 - leg**2)}
