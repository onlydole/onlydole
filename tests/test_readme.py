import pytest

from generator.readme import MarkerError, replace_region

DOC = "intro\n<!-- bento:start -->old stuff<!-- bento:end -->\nfooter\n"


def test_replace_region_swaps_body():
    out = replace_region(DOC, "bento", "NEW")
    assert "<!-- bento:start -->NEW<!-- bento:end -->" in out
    assert "old stuff" not in out
    assert out.startswith("intro\n")
    assert out.endswith("footer\n")


def test_replace_region_handles_multiline_body():
    out = replace_region(DOC, "bento", "\nline1\nline2\n")
    assert "<!-- bento:start -->\nline1\nline2\n<!-- bento:end -->" in out


def test_replace_region_missing_markers_raises():
    with pytest.raises(MarkerError):
        replace_region("no markers here", "bento", "NEW")


def test_replace_region_body_with_regex_specials():
    out = replace_region(DOC, "bento", r"path\1 and \g<0> and $&")
    assert r"path\1 and \g<0> and $&" in out
