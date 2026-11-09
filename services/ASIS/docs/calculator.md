# Offline Calculator Engine

Deterministic local mathematics for A.S.I.S.: SymPy-backed symbolic
and numeric computation behind a safe parser. The engine is the source
of truth for calculation results — the LLM translates natural language
into structured calculator requests and explains results, but never
performs arithmetic itself.

## Architecture

```text
Natural Language Understanding
        ↓
       LLM
        ↓
 Structured Calculator Request (calculate tool call)
        ↓
 PermissionManager (LOW, auto-approved)
        ↓
 Deterministic Calculator Engine (SymPy + stdlib, local only)
        ↓
 Verification (independent re-computation)
        ↓
 Structured Result (exact + numeric + verification record)
        ↓
       LLM
        ↓
 Human-readable explanation
```

- `asis/calculator/parser.py` — notation normalization (`^`, `π`,
  `√()`, `°`, `3!`, implicit `2x`) + AST allowlist scan + restricted
  SymPy parse. No `eval`/`exec` on user input (guarded by test).
- `asis/calculator/evaluator.py` — arithmetic, scientific functions,
  trig with angle modes, complex operations.
- `asis/calculator/symbolic.py` — simplify/expand/factor/collect/
  substitute, equation + system solving (exact/none/infinite
  distinguished), inequalities in interval notation, limits,
  derivatives (incl. partial/gradient), integrals, series, ODEs.
- `asis/calculator/linalg.py` — vectors and matrices with dimension
  validation.
- `asis/calculator/geometry.py` — 2D/3D primitives, Pythagoras,
  triangle solving (ambiguous SSA returns every solution).
- `asis/calculator/stats.py` — statistics (population vs sample kept
  distinct), probability, number theory (bounded algorithms).
- `asis/calculator/units.py` — SI-based conversions with dimensional
  validation (`5 kg → m` rejected); temperature affine handled.
- `asis/calculator/applied.py` — physics, engineering (math only, no
  control), finance (pure math, stated assumptions, no connectivity).
- `asis/calculator/constants.py` — math + CODATA 2022 physical
  constants with units and sources.
- `asis/calculator/engine.py` — operation dispatch + independent
  verification + resource limits.
- `asis/tools/provided/calculator_tools.py` — `calculate` tool
  (`operation` + string args), shared routers for GENERAL/CODING/
  TRANSLATION, voice via `app.chat()`, `asis calculate` CLI.

## Operations

`calculate`, `simplify`, `expand`, `factor`, `collect`, `substitute`,
`solve`, `solve_system`, `inequality`, `differentiate`, `partial`,
`gradient`, `integrate`, `limit`, `series`, `ode`, `trig`, `complex`,
`matrix`, `vector`, `geometry`, `triangle`, `statistics`,
`probability`, `number_theory`, `convert_units`, `constant`,
`physics`, `engineering`, `finance`.

## Syntax

```text
2 + 2 * 3          precedence, parentheses, unary minus
2x + 5             implicit multiplication
x^2  /  x**2       power aliases
sqrt(25)  √(...)   roots
sin(pi/6)          trig (radians default; sin(30°) or degrees mode)
3!                 factorial
1/3 + 2/7          exact rationals (→ 13/21, never 0.619...)
6.02e23            scientific notation
[[1,2],[3,4]]      matrices ([1,2,3] vectors, [1,2,3,4] datasets)
```

Rejected: `__import__`, `exec`, `eval`, `open(...)`, `os.system(...)`,
attribute traversal, or anything outside mathematics
(`CALCULATION_INVALID_EXPRESSION`).

## Precision

Exact-first: integers, rationals (`1/2`), radicals (`sqrt(2)`),
symbolic (`pi`) stay exact; decimals appear only in `numeric_result`
(rounded to `ASIS_CALCULATOR_PRECISION`, default 10). Complex results
carry symbolic exact form with numeric magnitude where finite.

## Units and constants

SI-based table (length, mass, time, temperature, area, volume, speed,
acceleration, force, pressure, energy, power, frequency, charge,
voltage, current, resistance, capacitance, inductance, angle) plus
aliases (`mile`, `celsius`, `°F`). Temperature units are `degC`/`degF`/
`degR`/`K` (bare `C`/`F` mean coulomb/farad). Physical constants cite
CODATA 2022 / SI-defining values with units in `constants.py`.

## Verification

Every applicable result carries `{method, match}`:

| Check | Method |
|---|---|
| arithmetic | independent float re-evaluation (lambdify path) |
| equations | back-substitution of each solution |
| factors | expand-and-compare |
| derivatives | finite-difference sampling |
| definite integrals | Simpson-rule quadrature |
| matrix inverse | A·A⁻¹ = I |
| unit conversion | round-trip recovery |

`match: false` means the engine disagrees with itself — treat the
result as suspect. `match: null` means no independent check applied.

## Resource limits

`ASIS_CALCULATOR_MAX_EXPRESSION_CHARS` (default 2000),
`ASIS_CALCULATOR_MAX_MATRIX_SIZE` (default 10),
`ASIS_CALCULATOR_TIMEOUT` (default 30, enforced by ToolExecutor),
dataset 10 000 values, polynomial degree 20, derivation order 10,
series order 12, 6×6 systems. Overflow yields `CALCULATION_TOO_COMPLEX`
/ `CALCULATION_INPUT_TOO_LARGE`, never a hang.

## Errors

`CALCULATION_DISABLED`, `CALCULATION_UNAVAILABLE` (SymPy missing),
`CALCULATION_TOO_COMPLEX`, `CALCULATION_INPUT_TOO_LARGE`,
`CALCULATION_INVALID_EXPRESSION`, `CALCULATION_DOMAIN_ERROR`,
`CALCULATION_DIMENSION_ERROR`, `CALCULATION_NO_SOLUTION`,
`CALCULATION_UNDEFINED`, `CALCULATION_TIMEOUT` — deterministic,
sanitized, no tracebacks.

## Offline and security

Pure local compute (SymPy + stdlib); no web, no cloud CAS, no model,
no telemetry. Works with DNS/HTTP unavailable (tested). Translated or
calculated text stays data — a result never becomes an instruction.

## Usage

```bash
asis calculate "2 + 2"
asis calculate "sqrt(144)"
asis calculate --operation solve --equation "x^2 - 5*x + 6 = 0" --variable x
asis calculate --operation integrate --expression "x^2" --variable x
asis calculate --operation convert_units --value 10 --from km --to mi
```

## Limitations

- SymPy is required (`pip install sympy`); without it the tool reports
  `CALCULATION_UNAVAILABLE`.
- Solvers handle polynomials and standard forms; unsupported ODEs /
  integrals fail explicitly instead of guessing.
- 3B-class symbolic edge cases (high-degree roots, special functions)
  return RootOf/exact forms rather than decimals.
- Live physical validation of constants: values are CODATA 2022 as
  documented per constant; re-verify against NIST for safety-critical
  use.
