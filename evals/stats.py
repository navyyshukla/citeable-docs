"""Numbers for the /evals page: every rate is a fraction with its n and a 95% range."""
from math import sqrt


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for k successes out of n. n == 0 gives (0.0, 1.0): no information.

    Better than the plain 'k/n plus or minus' range for the small n (15 to 30) used here: it
    never leaves [0, 1] and is not falsely tight at 0% or 100%.
    """
    if k < 0 or n < 0 or k > n:
        raise ValueError(f"need 0 <= k <= n, got k={k}, n={n}")
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def fraction_text(k: int, n: int) -> str:
    """'15/17 (66%–97%)', or 'no data' when n is 0."""
    if n == 0:
        return "no data"
    low, high = wilson(k, n)
    return f"{k}/{n} ({round(low * 100)}%–{round(high * 100)}%)"


def spread(values: list[float]) -> tuple[float, float]:
    """(min, max) across repeated runs."""
    if not values:
        raise ValueError("spread of no values")
    return (min(values), max(values))
