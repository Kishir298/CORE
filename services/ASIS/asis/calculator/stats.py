"""
Statistics, probability, and number theory over the standard library.

Means, spreads, quartiles, correlation, combinatorics, Bayes, prime
utilities, and modular arithmetic — all bounded and deterministic.
Population vs sample variance are never conflated: callers choose.
"""

from __future__ import annotations

import math
import statistics as _statistics

from asis.calculator import errors
from asis.calculator.validation import check_dataset_size


def parse_dataset(text: str, *, max_size: int = 10_000) -> list[float]:
    """Parse ``[1, 2, 3]`` or ``1, 2, 3`` into floats."""
    cleaned = text.strip()
    if cleaned.startswith("[") and cleaned.endswith("]"):
        cleaned = cleaned[1:-1]
    if not cleaned.strip():
        raise errors.domain_error("dataset must not be empty")
    try:
        values = [float(part) for part in cleaned.split(",") if part.strip()]
    except ValueError as exc:
        raise errors.invalid_expression(
            "dataset must be comma-separated numbers"
        ) from exc
    check_dataset_size(len(values), max_size=max_size)
    return values


def describe(text: str, *, sample: bool = True, max_size: int = 10_000) -> dict:
    """Descriptive statistics; ``sample`` selects sample variance/std."""
    values = parse_dataset(text, max_size=max_size)
    count = len(values)
    total = math.fsum(values)
    mean = total / count
    ordered = sorted(values)
    median = _statistics.median(values)
    try:
        mode = _statistics.mode(values)
    except _statistics.StatisticsError:
        mode = None
    variance = (
        _statistics.variance(values)
        if sample and count > 1
        else (_statistics.pvariance(values) if not sample else 0.0)
    )
    if sample and count == 1:
        stdev = 0.0
    else:
        stdev = _statistics.stdev(values) if sample else _statistics.pstdev(values)
    quartiles = _statistics.quantiles(values, n=4) if count >= 4 else []
    return {
        "count": count,
        "sum": total,
        "mean": mean,
        "median": median,
        "mode": mode,
        "min": ordered[0],
        "max": ordered[-1],
        "range": ordered[-1] - ordered[0],
        "variance": variance,
        "variance_type": "sample" if sample else "population",
        "stdev": stdev,
        "stdev_type": "sample" if sample else "population",
        "quartiles": quartiles,
    }


def weighted_mean(values_text: str, weights_text: str) -> float:
    values = parse_dataset(values_text)
    weights = parse_dataset(weights_text)
    if len(values) != len(weights):
        raise errors.dimension_error("values and weights lengths differ")
    total_weight = math.fsum(weights)
    if total_weight == 0:
        raise errors.domain_error("weights sum to zero")
    return math.fsum(v * w for v, w in zip(values, weights, strict=True)) / total_weight


def percentile(text: str, percent: str) -> float:
    values = parse_dataset(text)
    try:
        pct = float(percent)
    except ValueError as exc:
        raise errors.invalid_expression("percent must be numeric") from exc
    if not 0 <= pct <= 100:
        raise errors.domain_error("percent must be 0-100")
    return (
        _statistics.quantiles(sorted(values), n=100)[
            max(0, min(99, int(math.ceil(pct)) - 1))
        ]
        if len(values) >= 100
        else _percentile_simple(sorted(values), pct)
    )


def _percentile_simple(ordered: list[float], pct: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    rank = pct / 100 * (len(ordered) - 1)
    low, high = math.floor(rank), math.ceil(rank)
    if low == high:
        return ordered[int(rank)]
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def covariance(text_x: str, text_y: str, *, sample: bool = True) -> float:
    xs = parse_dataset(text_x)
    ys = parse_dataset(text_y)
    if len(xs) != len(ys):
        raise errors.dimension_error("datasets lengths differ")
    if len(xs) < 2:
        raise errors.domain_error("need at least two paired values")
    mean_x = math.fsum(xs) / len(xs)
    mean_y = math.fsum(ys) / len(ys)
    total = math.fsum(
        (x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)
    )
    return total / (len(xs) - 1 if sample else len(xs))


def correlation(text_x: str, text_y: str) -> float:
    xs = parse_dataset(text_x)
    ys = parse_dataset(text_y)
    if len(xs) != len(ys):
        raise errors.dimension_error("datasets lengths differ")
    try:
        return _statistics.correlation(xs, ys)
    except _statistics.StatisticsError as exc:
        raise errors.domain_error(f"correlation undefined ({exc})") from exc


def _non_negative_int(text: str, name: str, *, limit: int = 10_000) -> int:
    try:
        value = float(text)
    except ValueError as exc:
        raise errors.invalid_expression(f"'{name}' must be numeric") from exc
    if not value.is_integer() or value < 0:
        raise errors.domain_error(f"'{name}' must be a non-negative integer")
    result = int(value)
    if result > limit:
        raise errors.too_complex(f"'{name}' exceeds the {limit} limit")
    return result


def factorial_of(text: str) -> int:
    return math.factorial(_non_negative_int(text, "n", limit=1000))


def permutations(text_n: str, text_r: str) -> int:
    n = _non_negative_int(text_n, "n")
    r = _non_negative_int(text_r, "r")
    if r > n:
        raise errors.domain_error("r must not exceed n")
    return math.perm(n, r)


def combinations(text_n: str, text_r: str) -> int:
    n = _non_negative_int(text_n, "n")
    r = _non_negative_int(text_r, "r")
    if r > n:
        raise errors.domain_error("r must not exceed n")
    return math.comb(n, r)


def binomial_probability(trials: str, successes: str, prob: str) -> float:
    n = _non_negative_int(trials, "trials")
    k = _non_negative_int(successes, "successes")
    if k > n:
        raise errors.domain_error("successes must not exceed trials")
    try:
        chance = float(prob)
    except ValueError as exc:
        raise errors.invalid_expression("'p' must be numeric") from exc
    if not 0 <= chance <= 1:
        raise errors.domain_error("probability must be 0-1")
    return math.comb(n, k) * chance**k * (1 - chance) ** (n - k)


def bayes(prior: str, likelihood: str, evidence: str) -> float:
    try:
        prior_f, likelihood_f, evidence_f = (
            float(prior),
            float(likelihood),
            float(evidence),
        )
    except ValueError as exc:
        raise errors.invalid_expression("Bayes inputs must be numeric") from exc
    for name, value in (
        ("prior", prior_f),
        ("likelihood", likelihood_f),
        ("evidence", evidence_f),
    ):
        if not 0 <= value <= 1:
            raise errors.domain_error(f"{name} must be 0-1")
    if evidence_f == 0:
        raise errors.domain_error("evidence probability must be nonzero")
    return prior_f * likelihood_f / evidence_f


def expected_value(values_text: str, probs_text: str) -> float:
    values = parse_dataset(values_text)
    probs = parse_dataset(probs_text)
    if len(values) != len(probs):
        raise errors.dimension_error("values and probabilities lengths differ")
    if any(p < 0 for p in probs):
        raise errors.domain_error("probabilities must be non-negative")
    if not math.isclose(math.fsum(probs), 1.0, rel_tol=1e-6):
        raise errors.domain_error("probabilities must sum to 1")
    return math.fsum(v * p for v, p in zip(values, probs, strict=True))


def is_prime(text: str) -> bool:
    """Deterministic Miller-Rabin for 64-bit integers."""
    n = _non_negative_int(text, "n", limit=2**63 - 1)
    if n < 2:
        return False
    small = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    if n in small:
        return True
    if any(n % prime == 0 for prime in small):
        return False
    witness, power = n - 1, 0
    while witness % 2 == 0:
        witness //= 2
        power += 1
    for base in (2, 325, 9375, 28178, 450775, 9780504, 1795265022):
        candidate = base % n
        if candidate == 0:
            continue
        current = pow(candidate, witness, n)
        if current in (1, n - 1):
            continue
        for _ in range(power - 1):
            current = (current * current) % n
            if current == n - 1:
                break
        else:
            return False
    return True


def prime_factors(text: str) -> list[int]:
    n = _non_negative_int(text, "n", limit=10**12)
    if n < 2:
        raise errors.domain_error("factorization needs n >= 2")
    factors: list[int] = []
    candidate = n
    divisor = 2
    while divisor * divisor <= candidate and divisor <= 10**6 + 1:
        while candidate % divisor == 0:
            factors.append(divisor)
            candidate //= divisor
        divisor += 1 if divisor == 2 else 2
    if candidate > 1:
        factors.append(candidate)
    return factors


def gcd_of(*texts: str) -> int:
    if not texts:
        raise errors.invalid_expression("gcd needs at least one value")
    return math.gcd(*[_non_negative_int(item, "n", limit=10**18) for item in texts])


def lcm_of(*texts: str) -> int:
    if not texts:
        raise errors.invalid_expression("lcm needs at least one value")
    values = [_non_negative_int(item, "n", limit=10**12) for item in texts]
    result = 1
    for value in values:
        result = abs(result * value) // math.gcd(result, value) if value else 0
    return result


def mod_pow(base: str, exponent: str, modulus: str) -> int:
    try:
        b = int(float(base))
        exp_text = exponent.strip()
        negative = exp_text.startswith("-")
        exp = abs(int(float(exp_text)))
        mod = int(float(modulus))
    except ValueError as exc:
        raise errors.invalid_expression("modular inputs must be integers") from exc
    if mod <= 0:
        raise errors.domain_error("modulus must be positive")
    if exp > 10**7:
        raise errors.too_complex("exponent exceeds the 10^7 limit")
    result = pow(b, exp, mod)
    if negative:
        inv = pow(b, -1, mod) if math.gcd(b, mod) == 1 else None
        if inv is None:
            raise errors.domain_error("negative exponent needs coprime base/modulus")
        result = pow(inv, exp, mod)
    return result


def mod_inverse(a: str, modulus: str) -> int:
    try:
        base, mod = int(float(a)), int(float(modulus))
    except ValueError as exc:
        raise errors.invalid_expression("modular inputs must be integers") from exc
    if mod <= 0:
        raise errors.domain_error("modulus must be positive")
    try:
        return pow(base, -1, mod)
    except ValueError as exc:
        raise errors.domain_error("no modular inverse (not coprime)") from exc


def fibonacci(text: str) -> int:
    n = _non_negative_int(text, "n", limit=10_000)
    old, new = 0, 1
    for _ in range(n):
        old, new = new, old + new
    return old


def divisors(text: str) -> list[int]:
    n = _non_negative_int(text, "n", limit=10**9)
    if n == 0:
        raise errors.domain_error("divisors need n >= 1")
    found = set()
    root = math.isqrt(n)
    for candidate in range(1, root + 1):
        if n % candidate == 0:
            found.add(candidate)
            found.add(n // candidate)
    return sorted(found)
