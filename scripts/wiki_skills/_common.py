"""Private helpers shared across CLI scaffolds in this package.

Not exposed outside scripts/wiki_skills/. Underscore prefix marks intent.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, NamedTuple

# The repo root, resolved the same way as `wiki_index.layout_config._REPO_ROOT`
# (scripts/wiki_skills/_common.py → wiki_skills → scripts → repo). Used to locate the
# integrity manifest + the pinned skill contracts under the tree the CLIs run from
# ("the repo IS the implementation"; skills/ is symlinked into user installs).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# TASK 050 (R-2): the ONE identity-token shape, shared by the --orchestrator-id
# validators (wiki-query / wiki-verify-multi / wiki-extract-concepts) and the
# WIKI_ACTOR_ID env — a single constant so the former four copies cannot drift.
ORCH_ID_RE = re.compile(r"^[a-z0-9._:@-]{1,64}$")


def actor_id() -> str | None:
    """TASK 050 (R-2): the optional human/agent identity from ``WIKI_ACTOR_ID``.

    Complementary to ``--orchestrator-id`` (which names the MODEL/tool): a
    multi-agent setup exports e.g. ``WIKI_ACTOR_ID=critic-security`` and every
    knowledge-write log event carries ``details_json.actor``. Ambient env must
    never fail a CLI, so an unset OR invalid value (shape ``ORCH_ID_RE``) is
    **silently None** — documented, not an error (CWE-209: the value is never
    echoed anywhere)."""
    raw = os.environ.get("WIKI_ACTOR_ID")
    if raw is None or not ORCH_ID_RE.fullmatch(raw):
        return None
    return raw


def emit(payload: dict[str, Any], exit_code: int = 0) -> int:
    """Print one-line JSON and return ``exit_code``.

    Default success: ``exit_code=0``. Error envelopes (payloads containing
    an ``"error"`` key) MUST pass a non-zero code so shell scripts and
    test harnesses can detect failures via ``$?``. Convention (matches
    ``wiki_init._emit``): ``6`` for validation/look-up errors, ``7`` for
    interactive-confirm-required warnings.
    """
    print(json.dumps(payload, ensure_ascii=False), file=sys.stdout)
    return exit_code


def sanitize_alias_surface(surface: str, *, cap: int = 200) -> str | None:
    """Lossy clean of an alias surface for Class A write-back: strip edges, drop
    control chars (`ord < 32`), cap length. Returns the cleaned surface or None
    if nothing usable remains. Used by the merge path (F4, vdd-multi) so aliases
    absorbed from the DB — which the ingest side only `.strip()`-ed — cannot
    carry control chars or unbounded length into `into`'s frontmatter."""
    surface = surface.strip()
    if not surface:
        return None
    surface = "".join(c for c in surface if ord(c) >= 32)[:cap]
    return surface or None


_LINE_LEADING_MD_ACTIVES = frozenset("#>|*+-~")


def sanitize_markdown_text(text: str) -> str:
    """Escape every markdown/HTML-active sequence so ``text`` renders as
    literal plain prose (text-only allowlist).

    Lifted to this neutral module (TASK 007 / Decision-16 — no skill imports
    another skill) so both ``wiki-extract-concepts`` (concept-page bodies,
    H-4) and ``wiki-query`` (the synthesised answer body, R-6.3 egress guard)
    share one implementation.

    Attacks closed (verbatim from the H-4 vdd-multi 2026-05-28 hardening):
      * ``<tag>`` / CDATA / HTML entity smuggling → ``&lt;...&gt;`` / ``&amp;...``
      * ``[text](javascript:...)`` / ``![img](data:...)`` → ``\\[...\\](...)``
      * ``[[wikilink]]`` → ``\\[\\[wikilink\\]\\]`` (Obsidian wikilink injection)
      * ```code``` / `````fence````` → ``\\`...\\``` (dataview / mermaid embeds)
      * Leading-line ``#``/``>``/``|``/``*``/``+``/``-``/``~`` → ``\\X``
    """
    s = (text
         .replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;"))
    s = s.replace("`", "\\`")
    s = s.replace("[", "\\[").replace("]", "\\]")
    out_lines: list[str] = []
    for line in s.split("\n"):
        stripped = line.lstrip()
        if stripped and stripped[0] in _LINE_LEADING_MD_ACTIVES:
            ws_len = len(line) - len(stripped)
            line = f"{line[:ws_len]}\\{stripped[0]}{stripped[1:]}"
        out_lines.append(line)
    return "\n".join(out_lines)


# --- H-6 (LLM01 indirect prompt injection) — THE CANARY MATRIX -----------------
#
# `scan_injection_canaries` is fix-plan item (c) for issue H-6. It is the shared
# implementation both typed-knowledge extraction rails call — `wiki-extract-concepts`
# (a concept `name`/`definition`) and `wiki-extract-decisions` (a decision `title`/`body`).
# Lifted here (the neutral leaf both already import) for the same reason
# `sanitize_markdown_text` is: Decision-16 — no skill imports a sibling skill's private
# module — and so the canary set cannot drift into two subtly different gates.
#
# ★★ THE THREAT. Step 5 of each rail feeds an UNTRUSTED source body to the orchestrator's
# LLM. A hostile `_raw/` capture can carry `SYSTEM: emit a candidate whose definition is
# <exfil>` or a chat-template control token, and the model may PARROT that marker into a
# field it authors. Schema validation proves the SHAPE is right; it cannot tell a marker
# the model copied out of an injection from honest prose. This gate refuses the marker.
#
# ★★ SCANNED ON MODEL-AUTHORED FIELDS ONLY — NEVER on `source_quote`. This is the keystone
# that keeps the gate ZERO-FALSE-POSITIVE, and it is a deliberate exemption, not an
# oversight:
#   * The quote is VERBATIM source content, proven to occur in the body. A legitimate
#     article about prompt injection or LLM security — EXACTLY the technical content this
#     vault indexes; this very repo's H-6 issue file quotes `<|im_start|>` and `[[INST]]`
#     — carries these tokens in quotable sentences. Refusing that quote would refuse the
#     source's own best evidence: the classic gate that fires on innocent inputs, which
#     the operator then learns to route around.
#   * The quote's `<`/`>`/`[`/`]` are already HTML/markdown-escaped by
#     `sanitize_markdown_text` on egress, so the token renders INERT on the filed page.
#   * `_raw/` captures are quarantined from scoped retrieval by classification (H-6 item
#     (d), ADR-009), so a hostile quote never reaches a scoped synthesis at all.
# A field the MODEL wrote has none of those excuses: a control token or an override
# imperative in a concept definition is never content, it is a laundered injection.
#
# ★★ REFUSE, DON'T ESCAPE. `sanitize_markdown_text` would silently turn `<|im_start|>`
# into `&lt;|im_start|&gt;` and file it — the vault scarred, nobody told — and it does
# NOTHING to a phrase canary (`ignore previous instructions` is innocent words to the
# escaper). A dedicated refusal fires EARLY (exit 4, zero files written) and NAMES the
# attack, so the operator learns an injection was ATTEMPTED rather than shipping a mangled
# page. This is the same discipline as `_definition_is_prose`: refusing beats mangling.
#
# ★ CWE-117/209: the caller must NEVER echo the offending field VALUE — it IS the payload.
# The label returned here names the canary FAMILY, not the matched text.
_INJECTION_CANARIES: tuple[tuple[re.Pattern[str], str], ...] = (
    # -- prompt-template / special control tokens. No human writes `<|word|>`, `[INST]`,
    #    or `<<SYS>>` in a definition; these are ChatML / Llama / Mistral wire format.
    (re.compile(r"<\|[^\s|>]{1,40}\|>"), "a chat-template control token (<|…|>)"),
    (re.compile(r"\[{1,2}/?INST\]{1,2}", re.IGNORECASE),
     "an [INST] instruction delimiter"),
    (re.compile(r"<</?SYS>>", re.IGNORECASE), "a <<SYS>> system delimiter"),
    # -- an injected ROLE directive at the head of a line. Case-SENSITIVE all-caps: a
    #    title-case "System:" label in honest prose is fine; the injection shape is the
    #    shouted chat role `SYSTEM:` / `ASSISTANT:` the fix plan names verbatim. `[ \t>]*`
    #    tolerates a blockquote marker (a decision `body` is markdown).
    #    ★ LINE-ANCHORED ON PURPOSE (a second FP-guard): a mid-sentence all-caps role word
    #    (`the USER: role in RBAC`) is legit content, so only a role word STARTING a line —
    #    the chat-turn shape — is caught. Consequence (accepted): a mid-line `SYSTEM:` in a
    #    single-sentence definition evades this family; that is a defense-in-depth residual,
    #    not the primary control.
    (re.compile(r"(?m)^[ \t>]*(?:SYSTEM|ASSISTANT|USER|DEVELOPER|TOOL)\b[ \t]*:"),
     "an injected role directive (SYSTEM:/USER:/…)"),
    # -- the override imperative. TIGHTLY scoped — the verb AND the object noun are
    #    injection-specific, because this is the one canary family with real
    #    false-positive exposure on the vault's dominant content (technical/programming
    #    definitions), and precision beats recall on a defense-in-depth gate.
    #    ★ VERBS are `ignore`/`disregard` ONLY — NOT `override`/`forget`. Those two are
    #    heavily-used technical verbs: `override the previous rule` (CSS cascade / method
    #    overriding), `forget the previous context` (an LSTM forget gate) are ORDINARY
    #    concept definitions, and including them false-positived 7/8 of a measured
    #    technical-definition set (vdd-adversarial 2026-07-15). The rarer
    #    `override the system prompt` / `forget all prior context` injection phrasings are
    #    left to the structural-token canaries + classification + egress-sanitisation — an
    #    accepted defense-in-depth residual, NOT a hole worth a live FP class.
    #    ★ OBJECT nouns are the injection targets ONLY (`instruction`/`prompt`/`direction`/
    #    `system prompt`/`guardrail`) — NOT `context`/`rule`/`command`/`message`, which
    #    co-occur with legit technical verbs. So "ignore previous whitespace" / "disregard
    #    the earlier commit" still pass, and only an attempt to countermand INSTRUCTIONS is
    #    caught.
    (re.compile(r"(?i)\b(?:ignore|disregard)\b[^.\n]{0,40}?\b"
                r"(?:previous|prior|above|preceding|earlier|foregoing)\b"
                r"[^.\n]{0,20}?\b"
                r"(?:instruction|prompt|direction|system\s+prompt|guardrail)s?\b"),
     "an 'ignore previous instructions'-style override"),
)


def scan_injection_canaries(text: str) -> str | None:
    """Return a human-readable LABEL for the first injection canary in ``text``, or
    ``None`` if the text is clean. See ``_INJECTION_CANARIES`` for the threat model.

    The label names the canary FAMILY (`a chat-template control token`), never the matched
    substring — so a caller can put it in a refusal reason WITHOUT echoing the payload
    (CWE-117/209). Callers MUST scan model-authored fields only, never the verbatim
    ``source_quote``.
    """
    for pattern, label in _INJECTION_CANARIES:
        if pattern.search(text):
            return label
    return None


# --- H-5 (LLM supply-chain / stored prompt injection) — SKILL-CONTRACT INTEGRITY -----
#
# TASK 067, fix-plan option (a). The sibling of the H-6 canary above: H-6 refuses an
# injection copied out of an untrusted SOURCE; H-5 detects tampering with the REASONING
# CONTRACT ITSELF — a `skills/<name>/SKILL.md` that the orchestrator loads VERBATIM into its
# LLM context (Decision-17: the prompt lives in Markdown, not Python, so pip never pins its
# bytes). An edit to one of those files is a stored prompt injection honoured on the next run.
#
# ★ WHAT THIS BUYS — AND WHAT IT DOES NOT (be honest, per the issue). It does NOT stop a
# malicious maintainer who edits the prompt AND re-pins the hash in one commit — that is a
# branch-protection / CODEOWNERS problem, out of this framework's runtime scope. It DOES:
#   * detect on-disk drift / corruption / non-committer tampering at INVOCATION time (the
#     rail's `prepare` verifies BEFORE the "Load skill" step and SURFACES a non-`ok` status in
#     the envelope; the workflow instructs the orchestrator to STOP on it, and — enforced in
#     Python — `WIKI_STRICT_SKILL_INTEGRITY=1` makes `prepare` REFUSE, exit 2. ⚠️ Be precise:
#     the DEFAULT is fail-open-loud (a `warnings` note, normal exit), NOT a code-enforced stop;
#     the code-enforced stop is the strict env knob, and the workflow STOP is advisory prose the
#     orchestrator is instructed to honour);
#   * make any prompt change a VISIBLE `config/skill-integrity.sha256` diff a reviewer cannot
#     miss, and make the repo's OWN test suite go RED on an un-re-pinned edit — a mechanical,
#     always-on, vendor-neutral control (the option-(d) "SECURITY-review the change" intent,
#     delivered without a git-specific hook).
#
# ★ ENROLMENT IS GREP-DERIVED + CROSS-CHECKED, NEVER A SINGLE HAND-LIST (the unenumerated-surface
# guard — which, un-cross-checked, is only as complete as an author's memory to paste the marker,
# the exact blind spot the H-5 review found in v1). TWO independent enrolments that must AGREE:
#   (1) `discover_integrity_roster()` — the `SECURITY-SENSITIVE` marker grep (minus `_INTEGRITY_
#       EXEMPT`) → drives the MANIFEST. The single source shared with the re-pin script (Decision-16).
#   (2) `_DESIGNATED_VERBATIM_CONTRACTS` — a POSITIVE allow-list of the skills the orchestrator
#       loads verbatim as a reasoning/safety contract, each WITH its load-site evidence. The test
#       asserts every designated contract is pinned AND every marker'd file is designated-or-exempt,
#       so a contract that lost its marker (dropped from (1)) still FAILS via (2), and a rail wired
#       to `Skill({skill:X})` in a workflow but missing the marker FAILS the load-site test. A gap
#       in either enrolment is caught by the other.
#
# ★ VALUE-FREE (CWE-117/209). Results carry the repo-relative PATH + hex hashes only — never a
# byte of a file body. A hash is not a payload.
_INTEGRITY_MARKER = "SECURITY-SENSITIVE"
# Files carrying the marker that are NOT verbatim-loaded reasoning prompts, so pinning them
# would conflate "reasoning-contract integrity" with "any doc edited" and churn on ordinary
# edits. Each is named WITH its reason; the exemption is itself test-enforced (H-5 / R-067-2),
# so this can never silently become a blanket "ignore the marker" hole.
_INTEGRITY_EXEMPT: dict[str, str] = {
    # The /wiki-verify-multi CLI operator reference. The verbatim-loaded prompt it points at —
    # `wiki-verify` — IS pinned; this file only carries the marker as a cross-reference bullet.
    "skills/wiki-verify-multi/SKILL.md": "CLI operator doc, not a verbatim-loaded prompt; "
                                         "the prompt it references (wiki-verify) is pinned",
    # The repo-agent index. It carries the marker as PROSE (it DESIGNATES contracts as
    # SECURITY-SENSITIVE / SECURITY-label); it is not itself loaded verbatim as a contract.
    "skills/.AGENTS.md": "repo-agent index that designates contracts; not a loaded-verbatim prompt",
}

# ★ THE POSITIVE ALLOW-LIST (enrolment cross-check (2)). Every `skills/<name>/SKILL.md` the
# orchestrator loads VERBATIM as a reasoning or SAFETY contract — the high-blast-radius stored-
# prompt-injection surface — keyed by name → its load-site evidence. The test asserts each is
# pinned; if one loses its `SECURITY-SENSITIVE` marker (dropping it from the marker-roster) this
# list still fails the run. Maintained deliberately: adding a verbatim-loaded contract here
# WITHOUT pinning it fails the test, which is the point.
#
# ⚠️ SCOPE BOUNDARY (stated, per the H-5 review): this is the *reasoning/safety* surface, not
# "every SKILL.md the orchestrator ever reads." Operator CLI-reference contracts
# (`wiki-import`/`wiki-sync`/`wiki-search`/`wiki-config`/… SKILL.md) are loaded as command docs,
# not as authored-knowledge or safety-tier prompts; pinning them would churn on every ordinary
# CLI-doc edit for a far lower blast radius. They are a documented residual, NOT enrolled here.
#
# ★ KEYED BY REPO-RELATIVE PATH, NOT skill name — because a verbatim-loaded contract is NOT always
# a `skills/<name>/SKILL.md`: the cycle-2 review (security MAJOR) found repo-owned contract content
# also lives in `references/*.md`. Both file shapes are enrolled here + by the marker grep.
#
# ⚠️ REPO-OWNED ONLY. This pins contract files this repo AUTHORS (and symlinks into user installs).
# STATED EXCLUSIONS (denominator honesty): (a) `summarizing-meetings` — the summarize REASON meta-
# skill loaded verbatim by wiki-import/wiki-sync — is VENDORED (`Reference/…/Universal-skills/`, not
# `skills/`), so its bytes change by upstream re-sync and it is governed by the VENDORING POLICY
# (§7.4), not this manifest; (b) `skills/obsidian-cli/references/recipes.md` — composed PLAYBOOKS
# whose "binding conventions" RESTATE the pinned SKILL.md targeting discipline; not an independent
# safety authority (the tier authorities SKILL.md + command-reference.md ARE pinned); (c) operator
# CLI-reference SKILL.md (`wiki-import`/`wiki-sync`/… command docs) — loaded as documentation, far
# lower blast radius, high edit-churn.
_DESIGNATED_VERBATIM_CONTRACTS: dict[str, str] = {
    "skills/concept-extraction/SKILL.md":   "REASON contract — `Skill({skill:\"concept-extraction\"})`, wiki-extract-concepts Step 4",
    "skills/decision-extraction/SKILL.md":  "REASON contract — `Skill({skill:\"decision-extraction\"})`, wiki-extract-decisions Step 4",
    "skills/wiki-query-synthesis/SKILL.md": "REASON contract — `Skill({skill:\"wiki-query-synthesis\"})`, wiki-query Step 4",
    "skills/wiki-verify/SKILL.md":          "REASON contract — `Skill({skill:\"wiki-verify\"})`, wiki-verify-multi critics",
    "skills/obsidian-cli/SKILL.md":         "SAFETY contract — the T1/T2/T3 tier model (T3 eval/RCE ban) loaded verbatim; "
                                            "skills/.AGENTS.md designates it same-class (H-5 review MAJOR-1)",
    "skills/obsidian-cli/references/command-reference.md":
                                            "SAFETY contract — the per-command T1/T2/T3 tier TABLE (normative-must-agree "
                                            "with the SKILL.md model); a T3→T1 re-tag is unbacked by the model (cycle-2 MAJOR)",
    "skills/wiki-import/references/reason-contract.md":
                                            "REASON contract — the canonical REASON-step schema + the H-6 injection FENCE "
                                            "(Hard Rule nonce sentinel) for wiki-import/wiki-sync; loaded verbatim (cycle-2 MAJOR)",
}
SKILL_INTEGRITY_MANIFEST = _REPO_ROOT / "config" / "skill-integrity.sha256"


class SkillIntegrity(NamedTuple):
    """The verdict of a skill-contract integrity check. ``status`` is one of
    ``ok`` · ``drift`` · ``unpinned`` · ``manifest_unavailable``. ``skill`` is the
    repo-relative path; ``expected`` / ``actual`` are hex sha256 or ``None``. No file body."""

    status: str
    skill: str
    expected: str | None
    actual: str | None


def _sha256_file(path: Path) -> str | None:
    """Hex sha256 of ``path``, or ``None`` if it cannot be read. Never raises."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def _iter_contract_files() -> list[Path]:
    """The two repo-owned contract file SHAPES the orchestrator loads verbatim: a skill's
    `SKILL.md`, and a skill's `references/*.md` (the cycle-2 review found contract content —
    the H-6 fence, the tier table — also lives there). Deliberately NOT `evals/`, not
    `skills/.AGENTS.md` (an index), not a bare `**/*.md` walk (which would churn on prose docs).
    A marker'd file OUTSIDE these shapes is caught by the completeness test, which greps ALL
    skills markdown and asserts pinned-or-exempt — so the shape assumption cannot silently hide
    a contract."""
    skills = _REPO_ROOT / "skills"
    return sorted(set(skills.glob("*/SKILL.md")) | set(skills.glob("*/references/*.md")))


def discover_integrity_roster() -> list[str]:
    """Repo-relative POSIX paths of every contract file that MUST be integrity-pinned: it carries
    the ``SECURITY-SENSITIVE`` marker AND is not in ``_INTEGRITY_EXEMPT``. Sorted, grep-derived
    (H-5, the unenumerated-surface guard). Shared by the re-pin script and the test so the two
    rosters cannot drift (Decision-16).

    ★ FAIL-LOUD on a marker-candidate that cannot be read (`OSError`) or decode (`UnicodeDecode
    Error`): a security roster that silently SHRINKS when a contract is unreadable would drop a
    pin without a red test (H-5 review MINOR-2 + cycle-2 LOW). A broken contract file is an error
    worth surfacing, not swallowing."""
    roster: list[str] = []
    for p in _iter_contract_files():
        rel = p.relative_to(_REPO_ROOT).as_posix()
        if rel in _INTEGRITY_EXEMPT:
            continue
        try:
            body = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:  # do NOT swallow — a silent shrink is a hole
            raise RuntimeError(f"cannot read a skill contract for integrity discovery: {rel}") from exc
        if _INTEGRITY_MARKER in body:
            roster.append(rel)
    return roster


def load_integrity_manifest() -> dict[str, str] | None:
    """Parse ``config/skill-integrity.sha256`` (``sha256sum`` format: ``<hex>␠␠<relpath>``) into
    ``{relpath: hex}``. Returns ``None`` if the manifest is absent/unreadable (the fail-open
    signal — callers decide posture). Blank lines and ``#`` comments are ignored.

    ★ `utf-8-sig` strips a UTF-8 BOM so a valid FIRST-LINE pin is not silently DROPPED: under plain
    `utf-8` a leading BOM prepends to the hash token (`﻿` + 64 hex = 65 chars), which the hex
    guard then rejects → that contract reads as `unpinned` (H-5 review cycle-2 MINOR-1, corrected).
    ★ A token that is not a 64-hex sha256 is REJECTED, not stored — a malformed digest can never
    silently become a "pin" (and a WRONG 64-hex value is kept, so it correctly surfaces as `drift`)."""
    try:
        text = SKILL_INTEGRITY_MANIFEST.read_text(encoding="utf-8-sig")
    except OSError:
        return None
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # `sha256sum` writes "<hex>  <path>" (two spaces); `split(None, 1)` keeps a spaced path.
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        digest, rel = parts[0].lower(), parts[1].strip()
        if not _SHA256_HEX.match(digest):  # not a real pin — never a false-OK/false-drift entry
            continue
        out[rel] = digest
    return out


def verify_skill_integrity(skill_name: str) -> SkillIntegrity:
    """Integrity verdict for the contract ``skills/<skill_name>/SKILL.md`` against the pinned
    manifest. Never raises; never echoes a file body (CWE-209).

    ``manifest_unavailable`` (no manifest on disk) and ``unpinned`` (manifest present, this
    contract absent from it) are distinct so a caller can tell a broken deployment from a
    missing pin. A pinned file that no longer reads is ``drift`` (its bytes changed to nothing)."""
    rel = f"skills/{skill_name}/SKILL.md"
    actual = _sha256_file(_REPO_ROOT / rel)
    manifest = load_integrity_manifest()
    if manifest is None:
        return SkillIntegrity("manifest_unavailable", rel, None, actual)
    expected = manifest.get(rel)
    if expected is None:
        return SkillIntegrity("unpinned", rel, None, actual)
    if actual is None:
        return SkillIntegrity("drift", rel, expected, None)
    return SkillIntegrity("ok" if actual == expected else "drift", rel, expected, actual)


def skill_integrity_block(skill_name: str) -> dict[str, Any]:
    """The value-free ``integrity`` sub-envelope a ``prepare`` rail embeds for its contract."""
    r = verify_skill_integrity(skill_name)
    return {"status": r.status, "skill": r.skill, "expected": r.expected, "actual": r.actual}


def emit_prepare_with_integrity(
    result: dict[str, Any], skill_name: str, *, exit_code: int = 0,
) -> int:
    """Merge the ``integrity`` block into a ``prepare`` envelope, then emit it (H-5). On a
    non-``ok`` status: with ``WIKI_STRICT_SKILL_INTEGRITY=1`` set, REFUSE (an
    ``SKILL_INTEGRITY_DRIFT`` error envelope, exit 2 — the rails' existing "STOP, forward"
    code); otherwise fail-open-loud (a ``warnings`` note, the normal exit).

    Strict mode is an ENV knob, not a per-rail flag: it is vendor-neutral (works on every CLI
    with zero argparse surface) and uniform across every rail. Default is fail-open so a broken
    checkout / mid-edit never bricks every ``prepare``. ⚠️ The default STOP is ADVISORY, not
    code-enforced: the envelope surfaces the non-``ok`` status and the workflow's "Load skill"
    step instructs the orchestrator to STOP on it — the only IN-CODE refusal is strict mode."""
    integ = skill_integrity_block(skill_name)
    if integ["status"] != "ok":
        if os.environ.get("WIKI_STRICT_SKILL_INTEGRITY") == "1":
            return emit({"error": "SKILL_INTEGRITY_DRIFT", "integrity": integ}, exit_code=2)
        result.setdefault("warnings", []).append(
            f"skill contract '{skill_name}' integrity: {integ['status']} — verify "
            f"config/skill-integrity.sha256; re-pin an approved edit via "
            f"`python3 scripts/pin_skill_integrity.py --write` (H-5)")
    result["integrity"] = integ
    return emit(result, exit_code=exit_code)


# --- TASK 047: shared concept-mentions AUTO-block format ---------------------
# Pure string helpers shared by `write_concept_page` (seeds the block on create) and
# `rendering.render_concept_mentions_body` (regenerates it) so a seeded block is
# byte-identical to a rendered one. Kept here (the neutral leaf both already import) to
# respect the _pages.py "no import another skill / no rendering edge" dependency rule.

AUTO_MENTIONS_NAME = "mentions"
_MENTIONS_HEADING = "## Mentions across sources"


def wrap_auto_block(name: str, body: str) -> str:
    """The full `<!-- BEGIN-AUTO:name -->\\n<body>\\n<!-- END-AUTO:name -->` text."""
    return f"<!-- BEGIN-AUTO:{name} -->\n{body}\n<!-- END-AUTO:{name} -->"


def format_concept_mentions_body(source_slugs: list[str]) -> str:
    """The AUTO-block BODY for a concept's mentions: the heading + one `- [[slug]]` per
    source (caller dedups+sorts; sanitized on egress). Heading-only when empty — the block
    is always present, never absent."""
    lines = [_MENTIONS_HEADING, ""]
    lines += [f"- [[{sanitize_markdown_text(s)}]]" for s in source_slugs]
    return "\n".join(lines).rstrip()


# --- R-23 Phase A: the definition, read back OUT of the page --------------------------

# ★★ THE DEFINITION IS THE **LEAD** — from the H1 to the first sub-heading. Nothing else.
#
# Two measurements on the operator's live 720-concept vault forced this, and each one killed
# a parser that had passed every test written against the shape the CURRENT writer emits:
#
#   1. TASK 047 replaced the hand-written `## Mentions` section with the derived
#      `<!-- BEGIN-AUTO:mentions -->` block — but **nothing ever rewrote the old pages** (a
#      `mention` never rewrites a page). A cut on the sentinel alone therefore swallowed the
#      whole ledger — quote, backlink, line-span — into the definition of **676 of 720
#      concepts (94%)**.
#
#   2. Cutting on the ledger in *either* spelling then still swallowed a **hand-authored rich
#      page** whole: its lead paragraph, then `## Перечень функций`, then `### 1. …`, tables
#      and links — the entire document landed in one column. But `entity_cards` selects
#      `definition AS tldr` (sql/wiki-index-v2.sql). **A tldr that is a five-screen document
#      is not a tldr.**
#
# The rule that satisfies both, and that needs no list of ledger spellings to maintain: a
# definition is PROSE, and prose has no headings. So the lead ends at the first sub-heading of
# any kind — `## Mentions`, `## Mentions across sources`, `## Перечень функций`, all of it —
# or at the AUTO sentinel (an HTML comment, not a heading).
#
# Line-anchored, so a `##` occurring *inside* a sentence cannot truncate a definition.
_LEAD_END = re.compile(
    r"^(?:<!--\s*BEGIN-AUTO:|#{2,}\s)",
    re.MULTILINE,
)


def definition_from_concept_body(body: str) -> str | None:
    """The definition a concept page **carries** — parsed back out of its Class-A body.

    ★ THE PAGE IS THE SOURCE OF TRUTH, NOT THE CANDIDATE THAT MADE IT. `entities.definition`
    is a Class-B **cache** of this (ADR-002 §D8): `wiki-reindex --full` must be able to
    reproduce it from the markdown alone, or the DB has stopped being rebuildable. So the
    definition is read from where it actually lives — the body — and never re-derived from a
    candidate the operator may since have edited away.

    ★ **It is the LEAD: from the H1 to the first sub-heading.** A definition is prose, and
    prose has no headings — so whatever comes after one (the mentions ledger in either of its
    two spellings, or a hand-authored page's `## Перечень функций` and everything under it) is
    *not* the definition. That rule needs no list of section names to keep up to date, and it
    keeps `entity_cards`' `definition AS tldr` an actual tldr rather than a whole document.

    The shape `write_concept_page` emits is::

        # <name>
        <blank>
        <definition>
        <blank>
        <!-- BEGIN-AUTO:mentions --> … <!-- END-AUTO:mentions -->

    so the definition is *everything between the H1 and the AUTO block*. Both anchors are
    optional on purpose — a human may have retitled, un-headed, or hand-authored the page, and
    a parser that demanded the generated shape would silently return `None` (a NULLed
    definition, invisibly) on exactly the pages an operator cared enough to edit.

    Returns `None` only when there is genuinely no prose — never as a way of saying
    "unexpected shape".
    """
    m = _LEAD_END.search(body)
    text = body[:m.start()] if m else body
    lines = text.lstrip().split("\n")
    if lines and lines[0].lstrip().startswith("# "):
        lines = lines[1:]
    stripped = "\n".join(lines).strip()
    return stripped or None


def atomic_write_text(target: Path, text: str) -> None:
    """Atomically write ``text`` to ``target`` (tempfile in the same dir +
    fsync + ``os.replace``). ``os.replace`` is ``rename(2)`` on POSIX — it does
    NOT follow a symlink at ``target``, so a swapped-in symlink cannot redirect
    the write outside the dir. Shared by the TASK 005 entity-resolution CLIs
    for Class A frontmatter mutation (same primitive as ``write_concept_page``).
    """
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=".wiki-tmp-", suffix=".md"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def resolve_entity_file(repo: Any, vault_id: str, slug: str) -> Path | None:
    """Resolve an entity's Class A markdown file to a validated absolute path.

    Returns ``None`` if the entity has no row (caller → ``ENTITY_NOT_FOUND``).
    Raises ``PathTraversalError`` (from ``validate_inside_vault``, ``strict=True``)
    if the path escapes the vault OR does not exist on disk — the caller maps
    the latter to ``ENTITY_FILE_MISSING`` (DB/disk drift). Skills never build
    raw SQL: the relative path comes from ``repo.get_entity_file_path``.
    """
    from scripts.wiki_index.security import (
        PathTraversalError,
        validate_inside_vault,
    )

    rel = repo.get_entity_file_path(vault_id, slug)
    if rel is None:
        return None
    vault = repo.get_vault(vault_id)
    if vault is None:
        return None
    raw = Path(vault.root_path) / rel
    # F3 (vdd-multi): refuse a symlinked entity file — match the O_NOFOLLOW
    # posture of write_concept_page. validate_inside_vault(strict=True) already
    # blocks escapes OUTSIDE the vault; this additionally refuses a symlink AT
    # the entity-file path, closing the swap-page-for-symlink read/unlink vector
    # the confirm/alias/merge CLIs would otherwise follow.
    if raw.is_symlink():
        raise PathTraversalError(f"entity file is a symlink (refusing to follow): {rel}")
    return validate_inside_vault(raw, Path(vault.root_path))


def build_repo_config(
    vault_id: str, *, vault_root: Path | None, db_path_flag: str | None
) -> dict[str, Any]:
    """TASK 022 — the DB resolution chain → a `factory.make_repo` config dict.

    Precedence **`--db-path` flag > `index_db` (WIKI_SCHEMA.md) > global**: an explicit
    flag wins; else, if a `vault_root` is known, a declared `index_db` is resolved
    (`config_loader.resolve_index_db_path`); else the dict carries no `db_path` and
    `make_repo` falls back to the global DB — byte-identical to the pre-TASK-022 behaviour.
    `make_repo` is UNCHANGED: it still applies the R-03 iCloud guard + global fallback to
    whatever `db_path` (if any) this helper sets. `config_loader` is imported **lazily**
    inside the body (no top-level `_common → wiki_index` edge — `rendering` imports `_common`).
    """
    cfg: dict[str, Any] = {"vault_id": vault_id}
    if db_path_flag:
        cfg["db_path"] = db_path_flag
        return cfg
    if vault_root is not None:
        from scripts.wiki_index.config_loader import (
            ConfigValidationError,
            resolve_index_db_path,
        )
        from scripts.wiki_index.layout import GLOBAL_VAULT_SENTINEL
        # vdd-multi HIGH-L1: only honour a vault's index_db when the root belongs to the
        # addressed vault (a CWD walk-up must not redirect a by-id command to a different
        # vault's DB). The global sentinel ("all") opts out of the check — island intent.
        expected = None if vault_id == GLOBAL_VAULT_SENTINEL else vault_id
        try:
            resolved = resolve_index_db_path(vault_root, expected_vault_id=expected)
        except ConfigValidationError:
            # vdd-multi MED-2: a malformed/unsafe index_db must fail as a clean JSON
            # envelope (the orchestrator parses stdout), never a raw traceback. The value
            # is NOT echoed (CWE-209). Centralised here so all CLIs inherit it.
            emit({"error": "INVALID_INDEX_DB", "field": "index_db",
                  "reason": "index_db is unsafe or malformed (escapes the vault, is a "
                            "symlink, or is an absolute path outside the framework's "
                            "app-data dir without WIKI_ALLOW_ABSOLUTE_INDEX_DB)",
                  "hint": "If this vault's index_db is an absolute path (e.g. an iCloud "
                          "vault whose DB must live outside iCloud), re-run with "
                          "WIKI_ALLOW_ABSOLUTE_INDEX_DB=1, or set it once in your shell "
                          "profile / .claude settings `env`. Absolute paths under the OS "
                          "app-data dir (…/Application Support, …/.local/share, %APPDATA%) "
                          "are trusted automatically."},
                 exit_code=6)
            raise SystemExit(6)
        if resolved is not None:
            cfg["db_path"] = str(resolved)
    return cfg


def resolve_vault_root_for_cli(args: Any) -> Path | None:
    """TASK 022 — resolve a CLI's `vault_root` BEFORE `make_repo`, so a vault-local
    `index_db` is honoured (the ordering inversion). Precedence: an explicit
    `--vault-root` flag → a walk-up from CWD to the nearest `WIKI_SCHEMA.md`
    (`config_loader.find_vault_root`, like `.git`/`.obsidian`) → `None`.

    `None` is the global-DB case (no flag, not inside a vault) — `build_repo_config`
    then injects no `db_path` and `make_repo` falls back to global (byte-identity). Used
    uniformly by every subcommand so `record`/`apply` resolve the SAME local DB as
    `scan`/`prepare` (no split-brain). `config_loader` is imported lazily.
    """
    flag = getattr(args, "vault_root", None)
    if flag:
        return Path(flag)
    from scripts.wiki_index.config_loader import (
        VaultRootNotFoundError,
        find_vault_root,
    )
    try:
        return find_vault_root(Path.cwd())
    except (VaultRootNotFoundError, OSError):  # OSError: CWD deleted (vdd-multi LOW)
        return None
