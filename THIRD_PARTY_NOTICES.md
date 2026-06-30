# Third-Party Notices

This project incorporates code and content from third-party sources. The list
below acknowledges those sources and documents the licensing posture for each.

---

## wiki-ingest (vendored Python package)

- **Project name**: `wiki-ingest`
- **Upstream repo path**: `Universal-skills/skills/wiki-ingest/`
- **Vendored location in this repo**: `scripts/wiki_ingest/`
- **License (SPDX)**: `Apache-2.0` — verbatim copy of upstream's license at
  `Universal-skills/LICENSE` is preserved at
  [`scripts/wiki_ingest/LICENSE-upstream`](scripts/wiki_ingest/LICENSE-upstream)
  for unambiguous provenance per the Apache-2.0 redistribution requirements
  (§4 — retain license + notice).
- **Operator ownership note**: Both `obsidian-llm-wiki` (this repo) and
  `Universal-skills` (upstream) are owned by the same operator. No licensing
  friction today; the Apache-2.0 designation above reflects upstream's choice
  and keeps this repo's posture clean for future PyPI / open-source release
  (TASK 005+).
- **Snapshot commit SHA**: `b6080c10993cb9c2e2bc00e646b17c892b67e4a5`
- **Sync date (UTC)**: `2026-05-27T15:22:11Z`
- **Provenance + divergence log**:
  [`scripts/wiki_ingest/VENDORED_FROM.md`](scripts/wiki_ingest/VENDORED_FROM.md)
  records the source path, sync commit, per-file SHA256 hashes, and any local
  patches applied during vendoring (see `local_patches[]` section). Operators
  refreshing the snapshot via `bash scripts/sync_wiki_ingest.sh` will see this
  file rewritten with new metadata; the LICENSE-upstream copy and this notices
  entry are stable across syncs.

### Local modifications to the vendored copy

Local patches are documented in
[`scripts/wiki_ingest/VENDORED_FROM.md::local_patches`](scripts/wiki_ingest/VENDORED_FROM.md):

1. `__init__.py` — `sys.modules` vendoring shim (TASK 004 R-45 / bead 004-01).
2. `*` (package-wide) — `mypy --strict` escape hatch via `mypy.ini` override
   (TASK 004 R-50 / bead 004-04).
3. `commands/ingest.py` — programmatic `ingest()` + `IngestError` API
   extraction (TASK 004 R-46 / bead 004-03).

These patches are non-functional alterations to upstream behavior — they
adapt the package to in-process vendored use without changing its
documented API surface. Standalone usage of upstream `wiki-ingest`
(separate install) continues to work unchanged.

---

## External skills (referenced / integrated — NOT vendored)

> [!IMPORTANT]
> **Some of these external skills are governed by PROPRIETARY (closed-source)
> licenses.** They are integrated at runtime — installed separately by the
> operator and invoked by this framework — but their source is **not** copied
> into this repository. This repository's Apache-2.0 grant (see
> [`LICENSE`](LICENSE)) covers **only** the code in this repo and does **NOT**
> extend to any of the external skills listed below. Before redistributing,
> bundling, or commercially using any of these skills, you **must** consult and
> comply with each skill's own license terms — open-source terms cannot be
> assumed.

This framework calls the following skills as external dependencies (they live
under `Universal-skills/skills/` and/or are installed into the agent runtime,
e.g. `summarizing-meetings`, `transcript-fetcher`, `html`, `pdf`, `docx`).
Integration points: the `summarizing-meetings` REASON harness behind
`wiki-import` / `wiki-enrich`, and the `transcript-fetcher` / `html` / `pdf`
fetch+convert wrappers (ADR-001, ARCHITECTURE.md §2.3).

- **Licensing posture**: **varies per skill — some are proprietary**, others are
  open-source. There is no blanket license across this skill set. Treat each as
  an independently-licensed third-party component.
- **No grant by this repo**: nothing in this repository, including its
  Apache-2.0 license, conveys any right to use, copy, modify, or redistribute
  these external skills. Their respective owners reserve all rights not granted
  by their own licenses.
- **Operator responsibility**: the operator who installs and runs these skills
  is responsible for holding a valid license to each one. This repository
  references them by contract/API only and ships none of their source.
