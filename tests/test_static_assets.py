"""Static-asset guards for the web frontend.

The pages are ES modules, so nothing a script declares is visible to an
inline ``onclick="..."`` handler in HTML. One such handler survived the
module conversion (``handReplay.close()`` in replay.js) and broke the
replay's close buttons; this test keeps every handler in addEventListener.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

STATIC_DIR = Path(__file__).parent.parent / "gin_rummy" / "web" / "static"
INLINE_HANDLER = re.compile(r"""\bon[a-z]+\s*=\s*["'`]""")
ASSETS = sorted(p for p in STATIC_DIR.rglob("*") if p.suffix in {".js", ".html"})


@pytest.mark.parametrize("asset", ASSETS, ids=lambda p: str(p.relative_to(STATIC_DIR)))
def test_no_inline_event_handlers(asset: Path) -> None:
    hits = [
        f"{asset.relative_to(STATIC_DIR)}:{n}: {line.strip()}"
        for n, line in enumerate(asset.read_text().splitlines(), 1)
        if INLINE_HANDLER.search(line)
    ]
    assert not hits, "inline handlers can't see module scope; use addEventListener:\n" + "\n".join(hits)


def test_guard_sees_assets() -> None:
    assert any(p.name == "replay.js" for p in ASSETS)
