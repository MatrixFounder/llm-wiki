"""S1 — content-type detection for the unified construct path (TASK 039, R-2).

Decides WHICH REASON harness a source needs — independent of vault layout. The
detection is advisory: the orchestrator (not the CLI) runs the chosen harness
(Decision-17). `prepare` reports the kind + harness + confidence; `--kind`
overrides `auto`.
"""
from __future__ import annotations

import re
from typing import Any

KINDS = ("meeting", "lesson", "article", "paper", "thread", "summary", "auto")

# kind → the REASON harness the orchestrator should run for it.
# `summarizing-meetings` is the ONE universal content harness (it auto-detects + handles
# meetings AND articles/papers/threads, emitting the reason-contract note-JSON); a separate
# `summarizing-articles` would be redundant. `summary` is already finished → no REASON.
# `lesson` (TASK 046) is a transcript variant → the same universal harness; the educational
# `generate-detailed-meeting-summary` overlay + the pyramid note grammar are recipe/apply-side
# concerns, not a separate harness. `lesson` is opt-in via `--kind` (never auto-detected — a
# lecture is indistinguishable from a meeting by transcript shape alone).
KIND_HARNESS: dict[str, str] = {
    "meeting": "summarizing-meetings",
    "lesson": "summarizing-meetings",
    "article": "summarizing-meetings",
    "paper": "summarizing-meetings",
    "thread": "summarizing-meetings",
    "summary": "none",
}

_TS_RE = re.compile(r"^\s*\[?\(?\d{1,2}:\d{2}(?::\d{2})?\)?\]?", re.MULTILINE)
_TURN_RE = re.compile(r"^[ \t]*[A-ZА-ЯЁ][\w .'\-]{0,30}:\s", re.MULTILINE)
_THREAD_HOSTS = ("x.com/", "twitter.com/", "nitter.")
_PAPER_HOSTS = ("arxiv.org", "researchgate.net", "dl.acm.org", "ssrn.com")


def harness_for(kind: str) -> str:
    # default to the universal harness for any unmapped/unknown kind (never the deleted skill)
    return KIND_HARNESS.get(kind, "summarizing-meetings")


def _looks_like_transcript(body: str, low: str | None = None) -> bool:
    head = body[:20000]
    ts = len(_TS_RE.findall(head))
    turns = len(_TURN_RE.findall(head))
    low = low if low is not None else body.lower()  # reuse caller's lower() (1× over the body)
    markers = sum(m in low for m in
                  ("участник", "спикер", "participant", "speaker", "transcript", "стенограмма"))
    return ts >= 4 or turns >= 6 or (markers >= 2 and (ts >= 1 or turns >= 2))


def detect_kind(raw_text: str | None, source: str | None,
                frontmatter: dict[str, Any] | None = None) -> tuple[str, str]:
    """Return (kind, confidence ∈ {high,medium,low}). `auto`-resolution heuristics."""
    fm = {str(k).lower(): v for k, v in (frontmatter or {}).items()}
    body = raw_text or ""
    low = body.lower()   # computed ONCE over the (up-to-64 MiB) body, reused below
    src = (source or "").lower()

    # 1. already a finished summary (frontmatter signals)
    ftype = str(fm.get("type") or "").lower()
    if ftype.endswith("-summary") or ftype == "summary" or ("concepts" in fm and "related" in fm):
        return ("summary", "high")

    # 2. social thread
    if any(h in src for h in _THREAD_HOSTS):
        return ("thread", "high")
    if "## Post" in body or ("replies" in low and "Read " in body):
        return ("thread", "medium")

    # 3. academic paper
    if any(h in src for h in _PAPER_HOSTS):
        return ("paper", "high")
    if re.search(r"\barXiv:\s*\d", body) or ("Abstract" in body[:3000] and "References" in body):
        return ("paper", "medium")

    # 4. meeting transcript (speaker turns / timestamps / markers)
    if _looks_like_transcript(body, low):
        return ("meeting", "medium")

    # 5. default: a prose article
    return ("article", "low")
