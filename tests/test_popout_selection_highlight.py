"""TASK 070 (R-070-6) — the persisted selection highlight must reach popout windows.

The highlight's CSS used to be a `<style>` appended to `document.head`. A popout ("Move to new
window") is a SEPARATE document, so the rule never reached it: the CM6 ViewPlugin drew the mark,
and nothing styled it. The fix is `EditorView.baseTheme`, which makes CM6 mount the rule into
each EditorView's own root — popouts included, and re-mounted when a tab is dragged between
windows.

These are SOURCE-SHAPE tests, and that is a real limit: they pin that the plugin asks CM6 for a
base theme and never hand-injects a stylesheet. They cannot prove the rule renders — that
`var(--text-selection)` resolves inside a popout document is runtime behavior, and it is checked
by the live dogfood (TASK 070-08), not asserted from source here.

Both files are checked because `main.js` is what Obsidian actually executes. Since 070-05 it is
esbuild's output, so the two agree by construction — but a test that only read `main.ts` would
be checking a file the app never loads, which is the exact failure class this task exists to end.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_PLUGIN = Path(__file__).resolve().parents[1] / "skills/obsidian-cli/plugin/agent-bridge"
_MAIN_JS = _PLUGIN / "main.js"
_MAIN_TS = _PLUGIN / "main.ts"

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"^\s*//.*$", re.MULTILINE)


def _code_only(path: Path) -> str:
    """Source with comments stripped.

    Load-bearing, not tidiness: the first draft of `test_highlight_css_never_injected_into_one
    _document` FAILED the correct fix, because its regex matched the comment *explaining why*
    `document.head` is wrong. A source-grep test that greps its own rationale pins prose, not
    code — a gate that reports on nothing.
    """
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("src_path", [_MAIN_JS, _MAIN_TS], ids=["main.js", "main.ts"])
def test_highlight_css_is_a_cm6_base_theme(src_path: Path) -> None:
    code = _code_only(src_path)
    assert "EditorView.baseTheme" in code, (
        f"{src_path.name}: the highlight CSS must be a CM6 base theme so it mounts into every "
        f"editor's own document root (popouts are separate documents)."
    )
    assert "agent-persist-selection" in code


@pytest.mark.parametrize("src_path", [_MAIN_JS, _MAIN_TS], ids=["main.js", "main.ts"])
def test_highlight_css_never_injected_into_one_document(src_path: Path) -> None:
    """A stylesheet hand-mounted into one document is exactly the popout bug."""
    code = _code_only(src_path)
    for banned in ('createElement("style")', "createElement('style')", "head.appendChild"):
        assert banned not in code, (
            f"{src_path.name}: `{banned}` injects the rule into ONE document — the main window. "
            f"A popout would draw the selection mark with no rule to style it. Use "
            f"EditorView.baseTheme and let CM6 mount per root."
        )
