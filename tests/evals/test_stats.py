import pytest

from evals.stats import fraction_text, spread, wilson


def round_pair(p):
    return round(p[0], 2), round(p[1], 2)


def test_wilson_matches_figures_computed_in_this_project():
    assert round_pair(wilson(15, 17)) == (0.66, 0.97)
    assert round_pair(wilson(25, 26)) == (0.81, 0.99)
    low, high = wilson(9, 9)
    assert round(low, 2) == 0.70 and high == 1.0


def test_wilson_edges():
    assert wilson(0, 0) == (0.0, 1.0)  # no data: the widest honest range
    assert wilson(0, 10)[0] == 0.0


@pytest.mark.parametrize("k,n", [(11, 10), (-1, 5), (1, -5)])
def test_wilson_rejects_impossible_counts(k, n):
    with pytest.raises(ValueError):
        wilson(k, n)


def test_fraction_text():
    assert fraction_text(15, 17) == "15/17 (66%–97%)"
    assert fraction_text(0, 0) == "no data"


def test_spread():
    assert spread([3, 1, 2]) == (1, 3)
    with pytest.raises(ValueError):
        spread([])
