# Task 004-10: `THIRD_PARTY_NOTICES.md` + optional `scripts/wiki_ingest/LICENSE-upstream` [DOCS — no stub]

## Meta

- **Bead ID**: `task-004-10-third-party-notices`
- **Slug**: `third-party-notices`
- **Maps to**: Issue **I-V.10**; RTM rows **R-55**
- **Depends on**: `task-004-01-vendor-bootstrap` (needs snapshot SHA + sync date from `VENDORED_FROM.md`)
- **Estimated time**: 0.25 day
- **Priority**: Medium

## Use Case Connection

- **Cross-cutting** (legal / licensing posture): keeps the project ready for future PyPI / open-source release.

## Task Goal

Create (or update if exists) `THIRD_PARTY_NOTICES.md` at the repo root, crediting upstream `wiki-ingest`. Include: project name, upstream repo path, SPDX license identifier (or `"NOASSERTION — operator-owned, internal"` if upstream has no LICENSE file — Architect to confirm but operator owns both repos so internal-use is the practical default), operator ownership note, snapshot commit SHA, sync date. If upstream `Universal-skills/skills/wiki-ingest/` has a `LICENSE` file, copy it verbatim to `scripts/wiki_ingest/LICENSE-upstream` for unambiguous provenance.

## Stub-First Plan

**No stub phase** — direct write. Per `tdd-stub-first` skill, no code surface = no stub.

**Approach**:
1. Check if `Universal-skills/skills/wiki-ingest/LICENSE` (or `LICENSE.txt`, `LICENSE.md`) exists.
   - If yes: copy verbatim to `scripts/wiki_ingest/LICENSE-upstream`. Note its SPDX identifier (from the file header or detect via filename / `licenseref` tool if available).
   - If no: use `"NOASSERTION — operator-owned, internal"` per TASK.md R-55(a) operator-owned guidance.
2. Read `scripts/wiki_ingest/VENDORED_FROM.md` (from I-V.1) to extract `source_commit` and `synced_at`.
3. Write `THIRD_PARTY_NOTICES.md` at repo root with the structure below.
4. If a `THIRD_PARTY_NOTICES.md` already exists, append/update the `wiki-ingest` entry without disturbing other entries.

## Changes Description

### New Files

- `THIRD_PARTY_NOTICES.md` (at repo root). Structure:

  ```markdown
  # Third-Party Notices

  This project incorporates code and content from third-party sources. The list below
  acknowledges those sources and documents the licensing posture for each.

  ## wiki-ingest

  - **Project name**: `wiki-ingest`
  - **Upstream repo path**: `Universal-skills/skills/wiki-ingest/scripts/wiki_ingest/`
  - **License (SPDX)**: `<SPDX identifier from upstream LICENSE>` OR `NOASSERTION — operator-owned, internal`
  - **Operator ownership note**: Both `obsidian-llm-wiki` (this repo) and `Universal-skills` (upstream)
    are owned by the same operator. No licensing friction today; the SPDX identifier above is
    recorded for clarity in case of a future fork or open-source release.
  - **Vendored snapshot**: `scripts/wiki_ingest/` — see `scripts/wiki_ingest/VENDORED_FROM.md` for
    the live provenance metadata (sync timestamp, source commit SHA, per-file content hashes).
  - **Snapshot commit (at TASK 004 ship)**: `<40-char-SHA from VENDORED_FROM.md>`
  - **Snapshot sync date (at TASK 004 ship)**: `<ISO-8601 from VENDORED_FROM.md>`
  - **Refresh policy**: see `scripts/sync_wiki_ingest.sh` (manual snapshot refresh; no auto-sync).
    Divergent local patches in the vendored copy are listed in `VENDORED_FROM.md::local_patches`.

  _(append further third-party entries here as the project grows)_
  ```

- `scripts/wiki_ingest/LICENSE-upstream` (only if upstream has a LICENSE file — copied verbatim).

### Changes in Existing Files

- None (unless `THIRD_PARTY_NOTICES.md` already exists, in which case it's updated in place).

### Component Integration

- This bead is a documentation/legal artifact — no code, no tests.
- Cross-referenced from `VENDORED_FROM.md::source_path` (which already points to the upstream) and from the architect's §7.4 vendoring policy text.

## Files Touched (explicit list)

- `THIRD_PARTY_NOTICES.md` (new, at repo root)
- `scripts/wiki_ingest/LICENSE-upstream` (new — only if upstream has a LICENSE file)

## Test Surface

- **No automated tests**.
- **Manual verification**: Smoke 7 (TASK.md §7) includes a check that `VENDORED_FROM.md` has the required fields; this bead extends that posture to the `THIRD_PARTY_NOTICES.md` doc but doesn't add a new smoke.

## Acceptance

- [ ] R-55(a): `THIRD_PARTY_NOTICES.md` exists at repo root, lists `wiki-ingest` as a third-party source with: project name, upstream repo path, SPDX license identifier (or `NOASSERTION` placeholder), operator ownership note, snapshot SHA, sync date.
- [ ] R-55(b): If upstream `Universal-skills/skills/wiki-ingest/LICENSE` exists → `scripts/wiki_ingest/LICENSE-upstream` copied verbatim.
- [ ] R-55(c): Both files committed alongside the vendored copy (i.e., visible in `git status` after this bead, ready for the I-V.11 acceptance gate).

## Rollback

`rm THIRD_PARTY_NOTICES.md scripts/wiki_ingest/LICENSE-upstream` (the latter only if it was created). No other repo file is touched.

## Notes

- **Operator-owned-both-sides clarification**: per TASK.md R-55(a), the practical scenario is that both repos are owned by the same operator, so there's no immediate licensing friction. The notice file's purpose is **forward-looking** — making the licensing posture explicit so a future fork, contributor onboarding, or open-source release has zero ambiguity.
- If the architect or operator subsequently decides on a specific SPDX identifier (e.g., MIT, Apache-2.0), update this file in a follow-up bead — do not block TASK 004 on that decision.
- This bead may be **a no-op if `THIRD_PARTY_NOTICES.md` already exists with a `wiki-ingest` entry** (e.g., from an earlier draft). Confirm with the initial check.
