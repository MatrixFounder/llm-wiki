"""DF-072-2 — «`wiki-health` always exits 0» is FALSE, and had no falsifier anywhere.

Two halves, because the defect had two halves:

1. **The executed falsifier.** `tests/test_wiki_health.py` asserted `rc == 0` only on the
   SUCCESS path, so the unhedged claim could not go RED. Here the two reachable non-zero
   paths are RUN — `VAULT_NOT_FOUND` (6) and `INVALID_CLASS` (2) — alongside a success
   control (gaps found ⇒ still 0), so the *shape* of the true contract is pinned: exit 0
   on success, family codes on look-up/argument errors.

2. **The doc-truth gate.** The falsehood was manufactured by PARAPHRASE — the source
   docstring says "ALWAYS exits 0 **on success**" and every derived copy dropped the two
   words that made it true. A test that only checks the code cannot catch that, so this
   scans the live doc surface and requires every wiki-health "always exit 0" claim to
   carry a hedge. `tests/test_exit_code_doc_truth.py` covers exit-code TABLE ROWS; this
   claim is free prose in eight phrasings, which is why it slipped past it.

Archived records (`docs/tasks/`, `docs/plans/`, `docs/reviews/`, `docs/issues/`) are OUT
of scope by design: they record what was decided at the time and are not rewritten.
"""
from __future__ import annotations

import contextlib
import io
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_health

REPO_ROOT = Path(__file__).resolve().parent.parent
VAULT_ID = "health-exit-vault"


# ---------------------------------------------------------------------------
# 1. The executed falsifier — the claim can now go RED.
# ---------------------------------------------------------------------------

def _run(argv: list[str]) -> tuple[int, dict]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_health.main(argv)
    return code, json.loads(buf.getvalue())


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    """A registered vault with one page, so the success control is not vacuous."""
    vault, db = tmp_path / "vault", tmp_path / "g.db"
    (vault / "notes").mkdir(parents=True)
    (vault / "notes" / "req.md").write_text(
        "---\ntype: requirement\ntitle: R\ndate: 2026-08-08\nstatus: proposed\n---\n\nBody.\n",
        encoding="utf-8")
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=VAULT_ID, name="v", root_path=vault,
                              schema_version="7.0",
                              registered_at=datetime(2026, 8, 8)))
    repo.close()
    return vault, db


@pytest.mark.parametrize("sub", ["coverage", "ontology"])
def test_unknown_vault_exits_6_not_0(tmp_path: Path, sub: str) -> None:
    """DF-072-2 path 1. A typo'd vault name is NOT a clean health report — the
    documented-as-unconditional exit 0 would let a CI wrapper read it as one."""
    _vault, db = _seed(tmp_path)
    code, env = _run([sub, "--vault", "definitely-no-such-vault", "--db-path", str(db)])
    assert code == 6, "an unknown vault reported a clean bill of health"
    assert env["error"] == "VAULT_NOT_FOUND"


def test_invalid_class_exits_2_not_0(tmp_path: Path) -> None:
    """DF-072-2 path 2. `coverage --class <bogus>` is an argument error (family code
    2), not a report of zero gaps in a class that does not exist."""
    vault, db = _seed(tmp_path)
    code, env = _run(["coverage", "--vault", VAULT_ID, "--vault-root", str(vault),
                      "--db-path", str(db), "--class", "definitely-not-a-class"])
    assert code == 2, "a bogus --class was reported as zero gaps"
    assert env["error"] == "INVALID_CLASS"
    assert "definitely-not-a-class" not in json.dumps(env)  # CWE-209: no echo


def test_success_path_still_exits_0(tmp_path: Path) -> None:
    """The control — the half of the claim that IS true, and the half the fix must not
    break: a report (gaps or no gaps) exits 0."""
    vault, db = _seed(tmp_path)
    code, env = _run(["coverage", "--vault", VAULT_ID, "--vault-root", str(vault),
                      "--db-path", str(db)])
    assert code == 0 and env["action"] == "coverage"


# ---------------------------------------------------------------------------
# 2. The doc-truth gate — the paraphrase that manufactured the falsehood.
# ---------------------------------------------------------------------------

# Eight phrasings observed in the census; matched loosely on purpose. `[-\s]+` (not a
# single space) is load-bearing: the claim's most agent-facing instance — the `wiki-health`
# SKILL.md `description:`, wrapped by the YAML folded scalar as "ALWAYS\n  exits 0" and
# loaded into EVERY session's skill listing — is invisible to a single-line pattern. That
# is the same paraphrase blind spot one level up: the scan, not the docs.
_CLAIM_RE = re.compile(r"always[-\s]+exits?[-\s]+0", re.IGNORECASE)
# A hedge is anything that makes the claim TRUE: the two words the copies dropped, or an
# explicit statement of the non-zero codes. `DF-072-2` is the fourth kind — a passage that
# names the issue is DISCUSSING the false claim (ADR-006 D-036-5 has to quote it in order
# to correct it), not asserting it. A correction record that cannot quote what it corrects
# is a worse record than the escape hatch is a risk.
_HEDGES = ("on success", "0/2/6", "VAULT_NOT_FOUND", "INVALID_CLASS", "DF-072-2")
# A DIFFERENT, separately-documented claim (`wiki-verify-multi --fail-on=none`); its own
# hedge lives in skills/wiki-verify-multi/SKILL.md. Not this issue's surface.
_OTHER_CLI = ("--fail-on", "wiki-verify", "fail_on")
_CONTEXT = ("wiki-health", "wiki_health")
_WINDOW = 900  # attribution: a long README table cell puts the subject this far off
# The HEDGE window is deliberately much tighter than the attribution window. A reader
# meets the qualifier in the same breath as the claim or not at all — an exit-code table
# 800 chars away does not rescue a bare "always exit 0", and counting it as a hedge is
# how a wide window silently re-opened two sites mid-fix.
_HEDGE_WINDOW = 160

_ARCHIVED = ("docs/tasks/", "docs/plans/", "docs/reviews/", "docs/issues/",
             "docs/KNOWN_ISSUES.md",  # Class-B projection OF docs/issues/ — incl. this issue's own title
             "samples/", ".venv/", "node_modules/")


def _live_files() -> list[Path]:
    """Tracked .md/.py/.yaml, minus the archived record trees. `git ls-files` rather
    than a glob so an untracked scratch file cannot fail the gate.

    THIS FILE is excluded, and the exclusion is narrow on purpose. A scanner that hunts a
    phrase necessarily CONTAINS the phrase — five times, in comments explaining what it
    hunts — so it is the one file that quotes the claim without asserting it. The sibling
    `tests/test_wiki_health.py` is NOT excluded: it does assert the claim in its docstring,
    and it stays gated. (This only surfaced when the file was first COMMITTED: `git
    ls-files` cannot see an untracked file, so the gate could not scan itself until then.)
    """
    out = subprocess.run(["git", "ls-files", "*.md", "*.py", "*.yaml", "*.yml"],
                         cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    here = Path(__file__).resolve()
    return [p for rel in out.stdout.split()
            if not rel.startswith(_ARCHIVED)
            and (p := (REPO_ROOT / rel)).resolve() != here]


def _flatten(text: str) -> str:
    """Collapse line wraps and markdown emphasis before looking for a hedge. The FIRST
    version of this gate reported the one correct sentence in the repository — the source
    docstring's "ALWAYS exits 0 **on\\nsuccess**" — as unhedged, because the qualifier was
    split by a line wrap and a `**`. A literal-substring check over raw prose measures
    typography, not meaning."""
    return re.sub(r"\s+", " ", text.replace("*", "").replace("`", ""))


def _nearest(window: str, offset: int, tokens: tuple[str, ...]) -> int:
    """Distance from the claim (at `offset` within `window`) to the closest of
    `tokens`, or a large sentinel if none is present."""
    best = 10**6
    for tok in tokens:
        start = 0
        while (i := window.find(tok, start)) != -1:
            best = min(best, abs(i - offset))
            start = i + 1
    return best


def _claim_sites() -> list[tuple[str, int, str]]:
    """Every wiki-health `always exit 0` claim on a live surface → (rel, line, window).

    Attribution is by PROXIMITY, not by presence: a dense markdown table puts a
    `wiki-verify-multi --fail-on=none` row (a different, true claim) within the window
    of a genuine `wiki-health` row, and a presence test then silently DROPS the real
    site. Measured: that false-negative hid README.md and the manual's CLI table — two
    of the surfaces the issue names by name.
    """
    sites: list[tuple[str, int, str]] = []
    for path in _live_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        owned = "wiki_health" in path.name or "wiki-health" in str(path)
        for m in _CLAIM_RE.finditer(text):
            lo = max(0, m.start() - _WINDOW)
            window = text[lo:m.end() + _WINDOW]
            offset = m.start() - lo
            # A file whose PATH names wiki-health is in-context everywhere: its prose says
            # "it always exits 0" with no token to key on, so a text-proximity rule drops
            # the claim in the very module that owns it (measured: wiki_health.py:243 and
            # tests/test_wiki_health.py:176 both slipped through).
            d_health = 0 if owned else _nearest(window, offset, _CONTEXT)
            if d_health > _WINDOW or d_health >= _nearest(window, offset, _OTHER_CLI):
                continue  # out of scope, or the nearer subject is the other CLI
            line = text.count("\n", 0, m.start()) + 1
            hedge_ctx = text[max(0, m.start() - _HEDGE_WINDOW):m.end() + _HEDGE_WINDOW]
            sites.append((str(path.relative_to(REPO_ROOT)), line, _flatten(hedge_ctx)))
    return sites


def test_the_census_is_not_vacuous() -> None:
    """The guard this repo keeps relearning: a doc gate whose regex matches NOTHING
    reports clean forever. The claim is genuinely spread across ~15 live surfaces — if
    this drops to a handful, the scan broke, not the docs."""
    sites = _claim_sites()
    assert len(sites) >= 12, (
        f"the census found only {len(sites)} claim sites — the scan is broken, not the "
        "docs (DF-072-2 measured ~20 across CLAUDE.md, README.md, ARCHITECTURE.md, the "
        "ADR, both manuals, the ROADMAP, the skill and the source)")
    assert len({s[0] for s in sites}) >= 6, "the census collapsed to too few files"


def test_every_live_wiki_health_exit_claim_is_hedged() -> None:
    """DF-072-2. `wiki-health` exits 0 **on success**; look-up and argument errors still
    use the family codes (6 VAULT_NOT_FOUND, 2 INVALID_CLASS). An unhedged copy is the
    exact paraphrase that made an Accepted ADR assert something false."""
    unhedged = [f"{rel}:{line}" for rel, line, window in _claim_sites()
                if not any(h in window for h in _HEDGES)]
    assert not unhedged, (
        "unhedged «always exit 0» claim about wiki-health at:\n  "
        + "\n  ".join(unhedged)
        + "\n\nSay «exits 0 on success» (or name the codes: 6 VAULT_NOT_FOUND / "
          "2 INVALID_CLASS). The unqualified form is FALSE — see DF-072-2.")
