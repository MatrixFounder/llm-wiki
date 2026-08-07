"""TASK 072 bead 072-01 — no live contract may call a SHIPPED or RE-SCOPED roadmap item "deferred".

R-8 `wiki-verify-multi` shipped 2026-05-29 and R-7 `wiki-research` was re-scoped 2026-08-06, yet
promise sites across the tree still pointed callers at "deferred" entries — one of them inside a
SHA-256-pinned REASON contract loaded verbatim into the orchestrator's context. A stale promise in
a pinned contract is worse than a stale doc: the model reads it as current fact.

DESIGN NOTES — every one of these was a review finding, not a preference:

  G-1 · The population is GLOBBED, never hand-listed. A promise site added tomorrow is in scope
        without editing this file. The single exemption is named, reason-carrying, and asserted to
        EXIST — an exemption that rots into a typo exempts nothing while still looking deliberate.

  G-2 · Matching is PARAGRAPH-scoped with a bounded window, not per-line and not whole-file.
        Per-line misses the real defect: the pinned file's sentence WRAPS, so `R-8` and `deferred`
        sit on different lines. Whole-file is RED forever on `docs/ROADMAP.md`, which legitimately
        carries `deferred` on a dozen lines hundreds of lines away from the R-7/R-8 headings —
        the one file where the closure itself lives.

  Rule 4 · A synthetic fixture carrying the wrapped pattern must go RED. A gate that can pass by
        matching nothing is not a gate.

STATED LIMITATION — it matches CO-OCCURRENCE, not assertion polarity. A paragraph saying
"R-7 is NOT deferred" trips it exactly like one saying "R-7 is deferred". That is deliberate:
parsing English negation is the kind of overclaim this repo keeps paying for, and the false
positive is cheap to resolve at the writing end (say "not postponed", or put the closure in its
own paragraph). `docs/ROADMAP.md`'s R-7 closure is worded that way for this reason and says so.
Do NOT "fix" this by adding negation heuristics; do not fix it by exempting ROADMAP either — that
is the primary contract surface and exempting it would hollow the gate out.
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.wiki_skills._common import _REPO_ROOT

#: Forward-looking contract surfaces. GLOBBED — never a hand-list.
_ROOTS = ("docs", "skills", "workflows", "commands")

#: Per-task records and this task's own working documents. History and work-in-progress may
#: describe a state that was true when written; a forward promise may not.
_EXCLUDED_DIRS = ("docs/tasks/", "docs/plans/", "docs/archive/", "docs/reviews/", "docs/issues/")
_EXCLUDED_FILES = ("docs/TASK.md", "docs/PLAN.md")

#: ★ G-1 — ONE exemption, and the ruling that justifies it, verbatim:
#: `verification-map.md` is a per-task requirement-coverage record scoped to TASK 007 by its own
#: heading. It is HISTORY, not a forward promise, so a "deferred" inside it describes what was
#: true for TASK 007 rather than promising anything to a reader today.
_EXEMPT = ("docs/architectures/verification-map.md",)

#: Roadmap items that are NO LONGER deferred. Both must stay out of a "deferred" claim.
_ITEMS = (r"R-7\b", r"R-8\b")

_DEFERRED = re.compile(r"\bdeferred\b", re.I)

#: The two must co-occur within this many characters of normalised text. Wide enough to span the
#: pinned file's wrapped sentence; narrow enough that a ROADMAP paragraph mentioning R-7 and,
#: hundreds of lines later, some unrelated `deferred`, cannot collide.
_WINDOW = 200


def _candidate_files() -> list[Path]:
    """Every forward-looking markdown contract, discovered by walking — never transcribed."""
    out: list[Path] = []
    for root in _ROOTS:
        out.extend((_REPO_ROOT / root).rglob("*.md"))
    readme = _REPO_ROOT / "README.md"
    if readme.is_file():
        out.append(readme)
    keep = []
    for p in out:
        rel = p.relative_to(_REPO_ROOT).as_posix()
        if rel in _EXCLUDED_FILES or rel in _EXEMPT:
            continue
        if any(rel.startswith(d) for d in _EXCLUDED_DIRS):
            continue
        keep.append(p)
    return sorted(keep)


def _stale_promises(text: str) -> list[str]:
    """Paragraphs claiming R-7 or R-8 is deferred. Paragraph-scoped, whitespace-normalised.

    Returns the offending normalised paragraph excerpts, so a failure names WHAT is wrong rather
    than only where.
    """
    hits: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        norm = " ".join(para.split())
        for m_def in _DEFERRED.finditer(norm):
            for item in _ITEMS:
                for m_item in re.finditer(item, norm):
                    if abs(m_item.start() - m_def.start()) <= _WINDOW:
                        lo = max(0, min(m_item.start(), m_def.start()) - 40)
                        hits.append(norm[lo:lo + 260])
    return hits


# ------------------------------------------------------------------------------------------
# Controls — this gate must be able to FAIL.
# ------------------------------------------------------------------------------------------

def test_the_population_is_not_empty() -> None:
    """Non-vacuity: a glob that silently returns nothing would make every assertion below pass."""
    files = _candidate_files()
    assert len(files) >= 50, f"walked only {len(files)} contract files — the glob is broken"
    assert any(f.name == "SKILL.md" for f in files), "no SKILL.md in the population"
    assert any(f.as_posix().endswith("docs/ROADMAP.md") for f in files), "ROADMAP not in scope"


def test_the_matcher_fires_on_a_synthetic_wrapped_promise() -> None:
    """★ Rule 4 — the fixture carries the WRAPPED shape, which a per-line matcher would miss."""
    wrapped = (
        "## Out of scope\n\n"
        "- Multi-critic verification of the answer (ROADMAP **R-8 `wiki-verify-multi`** —\n"
        "  deferred). Both layer on top of this loop.\n"
    )
    assert _stale_promises(wrapped), "the matcher missed a wrapped R-8/deferred promise"
    assert _stale_promises("ROADMAP **R-7 `wiki-research`** — deferred."), "missed the R-7 form"


def test_the_matcher_does_not_fire_on_distant_co_occurrence() -> None:
    """The bounded window is what keeps docs/ROADMAP.md out — assert it, do not assume it."""
    far = "R-7 is re-scoped. " + ("filler word " * 40) + "something unrelated is deferred."
    assert not _stale_promises(far), "the window is too wide — a distant `deferred` collided"


def test_the_exemption_exists_and_is_reasoned() -> None:
    """An exemption that rots into a typo exempts nothing while still looking deliberate."""
    for rel in _EXEMPT:
        assert (_REPO_ROOT / rel).is_file(), f"exempted path {rel!r} does not exist"


# ------------------------------------------------------------------------------------------
# The assertion.
# ------------------------------------------------------------------------------------------

def test_no_live_contract_calls_r7_or_r8_deferred() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _candidate_files():
        hits = _stale_promises(path.read_text(encoding="utf-8"))
        if hits:
            offenders[path.relative_to(_REPO_ROOT).as_posix()] = hits
    assert not offenders, (
        "stale roadmap promises — R-8 `wiki-verify-multi` shipped 2026-05-29 and R-7 "
        "`wiki-research` was re-scoped 2026-08-06:\n"
        + "\n".join(f"  {f}\n    …{h}…" for f, hh in offenders.items() for h in hh)
    )
