"""The demo board builds from the shared lead_board/ sources. Regression: the build's leftover-marker
guard once matched the `__TEASER_STRIP_START__`/`_END__` comments the shared JS/HTML carry for the full
repo's teaser build, so the demo could not be built at all."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_demo_board as mod  # noqa: E402


def test_demo_builds_and_keeps_teaser_strip_comments() -> None:
    html = mod.build_html(mod.build_demo_data())
    assert "/*__" not in html
    assert "__TEASER_STRIP_START__" in html  # harmless comments in a non-teaser build


def test_an_unresolved_template_placeholder_still_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    original = mod._read
    monkeypatch.setattr(mod, "_read", lambda path: original(path) + "\n/*__NOT_SUBSTITUTED__*/" if path.name == "app.js" else original(path))
    with pytest.raises(ValueError, match="Unresolved"):
        mod.build_html(mod.build_demo_data())
