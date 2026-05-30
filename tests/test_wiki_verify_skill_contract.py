"""TASK 009 / bead 009-04 — pin the `wiki-verify` SKILL.md contract invariants.

Deterministic, no LLM. The enrichment (anti-bleed scoping + severity rubric + few-shot)
is prompt-only and MUST keep the verdict contract byte-stable: the lens/severity vocab
stays == the shipped gate enums, the H-6 armor + grounding-gate + "enforced in Python"
language stays present, and — because few-shot examples add an injection surface to a
file loaded verbatim into the orchestrator's context — every injection canary MUST sit
inside a code context (inline `...` or a ``` fence), never as a bare live directive
(arch F-2, the named defang control).
"""
from __future__ import annotations

import re
from pathlib import Path

from scripts.wiki_skills.wiki_verify_multi import _SEV_ORDER, _VALID_LENSES

_SKILL = Path(__file__).resolve().parents[1] / "skills/wiki-verify/SKILL.md"
# Injection canaries (compared case-INSENSITIVELY, mirroring the gate's `_is_fail`
# lower()-normalisation — sec-audit F-2). Includes the common chat-role / control
# tokens (sec-audit F-1 hardening). NOTE: this is a token allow-list, not a structural
# imperative-detector — a novel un-fenced directive phrasing outside these tokens could
# still pass; tracked as a TASK-009 LOW in KNOWN_ISSUES (future: structural check that
# the security-lens example region's directives are fenced).
_CANARIES = (
    "system:", "ignore previous", "ignore all previous",
    "<|im_start|>", "<|im_end|>", "[[inst]]", "[/inst]", "<<sys>>",
)
_INLINE_CODE = re.compile(r"`[^`]+`")


def _text() -> str:
    return _SKILL.read_text(encoding="utf-8")


def test_lens_vocab_matches_code_enum() -> None:
    """Every shipped lens is named in the prompt (drift between prompt + gate caught)."""
    t = _text()
    for lens in _VALID_LENSES:
        assert lens in t, f"lens '{lens}' (in _VALID_LENSES) not named in SKILL.md"


def test_severity_vocab_matches_code_enum() -> None:
    t = _text()
    for sev in _SEV_ORDER:
        assert sev in t, f"severity band '{sev}' (in _SEV_ORDER) not named in SKILL.md"


def test_h6_armor_preserved() -> None:
    t = _text().lower()
    assert "untrusted" in t, "H-6 untrusted-data framing missing"
    assert ("never obey" in t or "never as a command" in t or "not a command" in t), \
        "H-6 'never obey' rule missing"


def test_python_enforced_and_grounding_gate_preserved() -> None:
    t = _text()
    assert "enforced in Python" in t, "the 'verdict enforced in Python' contract is missing"
    assert "grounding gate" in t, "the grounding-gate language is missing"


def test_c2_backstop_documented() -> None:
    t = _text()
    assert "MUST NOT re-report an\ninjection" in t or "MUST NOT re-report an injection" in t \
        or "MUST NOT re-report" in t, "the C2 'logic/completeness MUST NOT re-report' rule is missing"
    assert "sanctioned" in t and "backstop" in t.lower(), "the C2 sanctioned-overlap framing is missing"


def test_anti_bleed_scoping_present() -> None:
    """Each lens declares an out-of-scope boundary (the anti-bleed core)."""
    t = _text()
    assert t.lower().count("out of scope") >= 3, \
        "expected an explicit 'out of scope' boundary on the scoped lenses"


def _fenced_line_flags(lines: list[str]) -> list[bool]:
    """Mark each line as inside a ``` fenced block (handles indented fences)."""
    inside, flags = False, []
    for ln in lines:
        is_fence = ln.lstrip().startswith("```")
        if is_fence:
            # the fence marker line itself is a boundary; treat as 'inside' (it carries
            # no canary prose) then toggle.
            flags.append(True)
            inside = not inside
        else:
            flags.append(inside)
    return flags


def test_skill_fences_are_balanced() -> None:
    """vdd-multi LOW-5: the canary-defang check trusts `_fenced_line_flags`, whose
    per-line in/out-of-fence state is only correct while ``` fences are BALANCED. An
    unbalanced fence (future edit) would invert the state for the file's tail and could
    mark a genuinely-bare canary as 'inside' (a false negative — the dangerous direction).
    Assert balance up front so a defang false-negative can't hide behind a stray fence."""
    n_fences = sum(1 for ln in _text().splitlines() if ln.lstrip().startswith("```"))
    assert n_fences % 2 == 0, f"unbalanced ``` fences in SKILL.md ({n_fences}) — defang check unreliable"


def test_injection_canaries_only_in_code_context() -> None:
    """The NAMED defang control (arch F-2): every injection canary appears ONLY inside a
    code context — a ``` fenced block OR an inline `...` span — never as a bare prose
    line that could read as a live directive."""
    lines = _text().splitlines()
    fenced = _fenced_line_flags(lines)
    offenders: list[str] = []
    for ln, in_fence in zip(lines, fenced):
        low = ln.lower()
        inline_spans = [s.lower() for s in _INLINE_CODE.findall(ln)]
        for canary in _CANARIES:
            if canary in low:
                inline_ok = any(canary in span for span in inline_spans)
                if not (in_fence or inline_ok):
                    offenders.append(f"{canary!r} bare in: {ln.strip()!r}")
    assert not offenders, "un-defanged injection canary (not in a fence/inline-code):\n" + "\n".join(offenders)
