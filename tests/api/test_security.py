from app.core.security import hash_password, tokens_match, verify_password


def test_password_round_trip():
    h = hash_password("tiny-sparrow-42")
    assert verify_password("tiny-sparrow-42", h)
    assert not verify_password("wrong", h)
    assert not verify_password("anything", "")


def test_tokens_match():
    assert tokens_match("abc", "abc")
    assert not tokens_match("abc", "abd")
    assert not tokens_match("", "")
