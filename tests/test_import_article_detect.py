"""S1 — `wiki_import_article._detect` content-type detection (R-2)."""
from __future__ import annotations

from scripts.wiki_skills.wiki_import_article import _detect


def test_harness_mapping():
    # one universal content harness — summarizing-meetings handles meetings AND articles
    assert _detect.harness_for("meeting") == "summarizing-meetings"
    assert _detect.harness_for("article") == "summarizing-meetings"
    assert _detect.harness_for("paper") == "summarizing-meetings"
    assert _detect.harness_for("thread") == "summarizing-meetings"
    assert _detect.harness_for("summary") == "none"
    # an unmapped/unknown kind must NOT return the deleted skill — default to the universal harness
    assert _detect.harness_for("auto") == "summarizing-meetings"
    assert _detect.harness_for("nonsense") == "summarizing-meetings"


def test_detect_finished_summary_by_frontmatter():
    k, c = _detect.detect_kind("body", "https://e.com/x", {"type": "meeting-summary"})
    assert k == "summary" and c == "high"
    k2, _ = _detect.detect_kind("body", "x", {"concepts": ["a"], "related": ["b"]})
    assert k2 == "summary"


def test_detect_thread_by_host():
    k, c = _detect.detect_kind("Some tweet text", "https://x.com/u/status/1", None)
    assert k == "thread" and c == "high"


def test_detect_paper_by_host():
    k, c = _detect.detect_kind("Abstract ... References", "https://arxiv.org/abs/2204.00251", None)
    assert k == "paper" and c == "high"


def test_detect_meeting_by_transcript_shape():
    transcript = "\n".join([
        "[00:01] Иван: всем привет, начнём встречу",
        "[00:05] Мария: да, по плану три темы",
        "[00:09] Иван: первая — релиз",
        "[00:14] Мария: action item на мне",
        "[00:20] Участник 3: согласен",
    ])
    k, _ = _detect.detect_kind(transcript, "file:///dropped.txt", None)
    assert k == "meeting"


def test_detect_article_default():
    k, c = _detect.detect_kind("A normal prose article about DeFi.\n\nParagraph two.",
                               "https://blog.example.com/defi", None)
    assert k == "article" and c == "low"
