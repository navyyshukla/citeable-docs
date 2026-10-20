import pytest

from evals.runner import RetrievalRow
from evals.threshold import ThresholdRow, threshold_table


def row(i, answerable, hit, score):
    return RetrievalRow(i, "hybrid", answerable, hit, ["x"], [score])


ROWS = [
    row("a", True, True, 0.033),    # strong and right
    row("b", True, True, 0.020),    # weak but right
    row("c", True, False, 0.031),   # strong but wrong
    row("d", False, None, 0.030),   # unanswerable, looks strong
    row("e", False, None, 0.010),   # unanswerable, weak
    row("f", True, False, 0.015),   # weak and wrong
]


def test_threshold_table_counts():
    t = {r.threshold: r for r in threshold_table(ROWS, [0.0, 0.025, 0.04])}
    # 0.0: everything is answered; wrong = c, d, e, f out of 6
    assert t[0.0] == ThresholdRow(0.0, 100.0, pytest.approx(4 / 6 * 100), 0.0)
    # 0.025: answered = a, c, d; wrong = c, d (2 of 3); abstained = b, e, f; e is a correct
    # abstention; correctly abstained % = unanswerable questions that abstained: 1 of 2
    assert t[0.025].answered_pct == pytest.approx(50.0)
    assert t[0.025].wrong_when_answered_pct == pytest.approx(2 / 3 * 100)
    assert t[0.025].correctly_abstained_pct == pytest.approx(50.0)
    # 0.04: nothing answered; wrong-when-answered is undefined, shown as None
    assert t[0.04].answered_pct == 0.0 and t[0.04].wrong_when_answered_pct is None
    assert t[0.04].correctly_abstained_pct == 100.0


def test_errors_and_missing_scores_count_as_nothing_found():
    r = RetrievalRow("g", "hybrid", False, None, [], [], error="boom")
    t = threshold_table([r], [0.01])[0]
    assert t.answered_pct == 0.0 and t.correctly_abstained_pct == 100.0


def test_empty_rows_give_an_empty_table_not_a_crash():
    assert threshold_table([], [0.01]) == []
