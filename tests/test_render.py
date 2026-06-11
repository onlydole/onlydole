from generator.render import fit


def test_fit_short_text_unchanged():
    assert fit("hello", 10) == "hello"


def test_fit_truncates_with_ellipsis():
    assert fit("a long title here", 8) == "a long…"


def test_fit_exact_length_unchanged():
    assert fit("12345678", 8) == "12345678"


def test_fit_collapses_internal_whitespace():
    assert fit("a\n  b\tc", 20) == "a b c"
