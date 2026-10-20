"""Checks that need no database: bad input must be refused before any connection is made."""
import pytest

from app.db import Db
from app.usage import Usage


@pytest.mark.parametrize("comment", ["bad\x00comment", "\ud800"])
def test_feedback_comment_with_nul_or_surrogates_is_refused_before_the_database(comment):
    usage = Usage(Db("postgresql://nobody@127.0.0.1:1/none"))  # would fail if it connected
    with pytest.raises(ValueError, match="not allowed"):
        usage.add_feedback(1, "00000000-0000-0000-0000-000000000000", 1, comment)
