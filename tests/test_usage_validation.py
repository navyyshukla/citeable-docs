"""Checks that need no database: bad input must be refused before any connection is made."""
import pytest

from app.db import Db
import secrets

from app.usage import Usage, looks_like_token


@pytest.mark.parametrize("comment", ["bad\x00comment", "\ud800"])
def test_feedback_comment_with_nul_or_surrogates_is_refused_before_the_database(comment):
    usage = Usage(Db("postgresql://nobody@127.0.0.1:1/none"))  # would fail if it connected
    with pytest.raises(ValueError, match="not allowed"):
        usage.add_feedback(1, "00000000-0000-0000-0000-000000000000", 1, comment)


def test_real_tokens_have_the_shape_the_check_accepts():
    assert all(looks_like_token(secrets.token_urlsafe(32)) for _ in range(200))


@pytest.mark.parametrize("junk", ["", "abc", "é" * 43, "a" * 42, "a" * 44, "a" * 42 + "=",
                                  "a" * 21 + " " + "a" * 21, "a" * 42 + "\n"])
def test_junk_does_not_look_like_a_token(junk):
    assert not looks_like_token(junk)
