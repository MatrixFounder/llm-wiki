---
id: ARCH-10-PHANTOM-CI
type: known-issue
status: open
opened_at: 2026-07-16
category: class-b-integrity
slug: arch-10-claims-a-ci-pipeline-that-does-not-exist
---

**Severity:** SEV-2 · **Area:** docs/architecture · **Discovered:** TASK 070's architecture review
(the reviewing agent died mid-stream; this partial finding survived and proved correct).

## What

`docs/ARCHITECTURE.md:196` (§10 Deployment) states the system has a
**"CI/CD pipeline (pytest + mypy --strict on PR)"**.

**There is none.** Verified 2026-07-16 at `a8f7a70`:

- no `.github/` (the only `**/.github/**` hits are inside `node_modules/@codemirror/*`)
- `grep "runs-on|uses: actions/|jobs:"` → no files
- no `Makefile`, `justfile`, `tox.ini`, `noxfile.py`, `.pre-commit-config.yaml`
- no active git hooks (`.git/hooks/` holds only `*.sample`)

## Why it matters — it silently weakens every gate that leans on it

The repo's strict-mode escape hatches are all documented as "CI sets it", and **nothing sets them**:

- **H-5** — `WIKI_STRICT_SKILL_INTEGRITY=1` (makes `prepare` REFUSE on contract drift) is set
  **only by `tests/test_h5_skill_integrity.py`'s own monkeypatch** (`:277`, `:291`). No runner,
  no hook, no pipeline sets it. The strict layer exists and fires for nobody.
- **TASK 070 / ARCH §2.2.3** — `WIKI_STRICT_PLUGIN_BUILD=1` (turns a drift-gate skip into a
  failure) inherits the same phantom trigger. Caught during that task and recorded there as
  **latent**, so the L0 hash-pin — which needs no toolchain and no env var — is what actually
  carries the non-vacuity guarantee.

This is the project's signature failure mode at the infrastructure layer: **a layer that looks
like enforcement while enforcing nothing**, because its activation condition is a document's
claim rather than a fact. Anyone reading §10 reasonably concludes "PRs are gated" and designs
accordingly — as TASK 070's own architecture section did, until this was checked.

## Options (not decided)

1. **Correct §10** to describe reality (gates are *local* — `pytest` + `mypy --strict` run by
   hand / by the agent pipeline), and re-word every "CI sets it" as "reserved for a future CI".
   Cheapest; makes the docs honest; leaves the strict flags latent-by-design.
2. **Add a real CI** (`.github/workflows/`) running `pytest`, `mypy --strict`, and setting both
   `WIKI_STRICT_*` flags — which is what the docs already promise. Makes the flags earn their
   keep, and would have caught the TASK-068 fabricated `save()` at PR time.
3. Both, in that order.

Until one lands, treat every `WIKI_STRICT_*` mode as **available but unfired**, and never count
it as a layer when arguing a gate is non-vacuous.
