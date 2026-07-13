# TASK 063-11 — H-6 hardening + no declassification pump + never author `aliases:`

**Phase**: 3 (apply validation) · **RTM**: R-063-10 · **Type**: code (security) · **Effort**: 3h
**Depends on**: 063-06 · **Unblocks**: 063-12

## Goal

The input is an **UNTRUSTED transcript** whose text lands in **YAML frontmatter** (`status:`, edge
lists) and page bodies. Three guarantees.

## (a) Injection + traversal (reuse the precedent's guards — do not re-invent them)

- `_sanitize_markdown_text` / `_sanitize_name` / `_sanitize_definition` — from
  `scripts/wiki_skills/_common` + `wiki_extract_concepts/_validation.py`.
- **The YAML-delimiter-injection guard** — a `status` (or any frontmatter-bound field) containing
  `\n---\n` would **break out of the frontmatter block** and inject arbitrary markdown/YAML.
- **`_is_valid_slug` as the traversal gate** — `supersedes: [[../../x]]` must be **refused**, not
  normalised. A candidate is untrusted model output about untrusted text: two layers of untrust.

Refusals here are **contract violations ⇒ exit 4, zero writes** (I-7).

## (b) ★ NO DECLASSIFICATION PUMP

A generated page **inherits the SOURCE page's `classification:`** whenever the vault declares a
`policy:` block.

**Honest statement of what this does today:** it is **inert**. Policy is declared-but-OFF (TASK 061
§5), and it does not affect the lint delta either — `classification-leak` fires only on `cited` /
`verifies` refs, which typed pages do not carry. *So this bead's (b) changes no observable behaviour
today, and saying so is the point.*

**Why do it anyway:** the moment R-16 is enabled, a decision extracted from a `confidential`
transcript that silently inherits `default_level` turns this rail into a **declassification pump** —
a security regression created by a *config flip elsewhere*, in a rail nobody re-audits. Inheriting
now costs one line; retrofitting it later costs an incident.

## (c) `apply` NEVER authors an `aliases:` key

Closes the `alias-collision` lint category **by construction** — not by validation. A category you
cannot enter needs no guard.

## Context — files

- **Edit** `_validation.py` (`_preflight_sanitize`, traversal gate), `_pages.py` (frontmatter render,
  classification inheritance).
- **Read** `wiki_extract_concepts/_validation.py` (`_is_valid_slug`, `_SLUG_RE`, `_preflight_sanitize`),
  `scripts/wiki_skills/_common.sanitize_markdown_text`, `scripts/wiki_index/policy.py::resolve_policy`.

## Tests (RED first) — `tests/test_extract_decisions_security.py` (new)

- `test_traversal_in_edge_target_refused` — `supersedes: ["../../etc/passwd"]` ⇒ exit 4, zero writes.
- `test_frontmatter_breakout_refused` — `status: "accepted\n---\nmalicious: true"` ⇒ exit 4. Then
  **also** assert no file on disk contains `malicious:` — refusing the *payload* and refusing the
  *write* are two different claims.
- `test_markdown_egress_is_sanitized` — a body with an injected `<script>` / raw HTML is sanitized on
  the write side (H-6 write-side egress).
- `test_classification_is_inherited_from_the_source` — source page `classification: confidential` ⇒
  the generated decision carries `classification: confidential`, **not** the vault `default_level`.
  **MUT:** drop the inheritance ⇒ RED. *The test must exist even though the behaviour is inert today —
  an inert guard with no test is a guard that silently disappears in the refactor before R-16 lands.*
- `test_apply_never_authors_aliases` — grep the written page's frontmatter keys: `aliases` absent, on
  **every** written page in a multi-candidate batch (not just the first).
- `test_error_messages_never_echo_the_payload` — CWE-209/117: the refusal envelope contains no
  control characters and no verbatim injected string.

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed. `mypy --strict scripts/` clean.
- [ ] **GREP-THE-SURFACES — "every field that lands in frontmatter is guarded" is a denominator
      claim.** Enumerate the frontmatter-bound fields **from the renderer**, not from memory:
      ```bash
      grep -n "frontmatter\|fm\[" scripts/wiki_skills/wiki_extract_decisions/_pages.py
      # → the exact key set written; assert the sanitizer covers EACH one, in a test that
      #   iterates that key set (so a NEW frontmatter key added later is covered automatically)
      ```
      A test that hardcodes `["status", "supersedes"]` would silently stop covering key #3.
- [ ] **MUT:** remove the YAML-delimiter guard ⇒ `test_frontmatter_breakout_refused` RED.
- [ ] Security review pass (`skill-adversarial-security`) on this bead's diff.

## Rollback

Revert the sanitizers → the tree stays green but the security tests go RED. Correct signal.
