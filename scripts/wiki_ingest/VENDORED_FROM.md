# Vendored From

This directory is a snapshot of `Universal-skills/skills/wiki-ingest/scripts/wiki_ingest/`.
Do **NOT** edit files here directly — fixes must land upstream first, then sync via
`bash scripts/sync_wiki_ingest.sh` (lands in I-V.2).

- **source_path**: `Universal-skills/skills/wiki-ingest/scripts/wiki_ingest/`
- **source_commit**: `b6080c10993cb9c2e2bc00e646b17c892b67e4a5`
- **synced_at**: `2026-05-27T15:22:11Z`
- **synced_by**: `bead 004-01-vendor-bootstrap` (manual `rsync -av --exclude=__pycache__ --exclude='*.pyc'`); I-V.2 sync script automates this.

## rsync exclude list

The initial sync (this bead) and the future `scripts/sync_wiki_ingest.sh` (I-V.2) MUST exclude:
- `__pycache__/` and `*.pyc` — Python bytecode (also blocked project-wide by `.gitignore:2`; verified).
- `.AGENTS.md` — upstream-specific package doc with cross-references to Universal-skills paths
  (e.g., `../../../../docs/tasks/task-015-...md`) that do not resolve in this repo. Keeping it
  would produce broken links and operator confusion. Excluded by deliberate choice, not by
  pattern; sync script must enforce.

## hashing convention

`sha256(file_bytes)` per `*.py` file, read in binary mode, no normalization.
Path is repo-relative to `scripts/wiki_ingest/` (POSIX separator). I-V.2's
`scripts/sync_wiki_ingest.sh` divergence-check reads this table.

## file_hashes (current — may include local patches)

| path | sha256 | diverged? |
|---|---|---|
| `__init__.py` | `392171dfdef6adc2eb13349c9cdc2e8ec2ce29ada0b96d77924f5afedcd77575` | yes (local_patches[0]) |
| `_classify.py` | `ea2ae05a9ac0a115919460996b795e358827e92027f51d0ac36fe51b1a685e47` | no |
| `_dispatch.py` | `77626683ebbb4b27f809aba2180551e7c3f843b623f7ebdfa7423d57a08165dc` | no |
| `_frontmatter.py` | `cbc9d5d154be1399f17a3b1a3793d2397cdaa1ff1271b5f22da05cf3961bbe77` | no |
| `_markdown.py` | `28075e0d0e2fe1df18256b4e1973d81c594789ca70c1c15edcfc6b871defef7c` | no |
| `_page_merge.py` | `b76becde42a31b1ad7d2e933f87852663bb899c1b4a626ca3ad0c8dd81e4b1f8` | no |
| `_safety.py` | `848caa37dbd480375783d885e16f58a23f30cf17cdede2df260af76aac03767a` | no |
| `_vault.py` | `6595d27e566d6f924a9e2a929189c93ff3caca98aeffbebc59d5fb0ed79fd655` | no |
| `commands/__init__.py` | `1bc2ba32bd72767b35d878c632591daf9f6324c58291637470b825c05668fb3a` | no |
| `commands/append_log.py` | `bb0bffedb34d646c3363b395bfa66c883c134fea876d3bf021418709a0e11db9` | no |
| `commands/classify_folder.py` | `ff639549440bac27fd4712165ffd82e717ce98355e8bfaa5ccce49d788912520` | no |
| `commands/demote.py` | `16b7b250608d4c9965928744ac660df93395ac9ed19483b7eee80c3ad1a61e16` | no |
| `commands/find.py` | `dd4fe1260eb42bf99031ddbb732503c892fc6be694a002b2d6b9fed3c02845ec` | no |
| `commands/ingest.py` | `d16026b9cbc820b4ab9117b52c11ebba66292e2f0d993d1030104d47d194f3b9` | no |
| `commands/init.py` | `271d4e105af6a0b739fb313d43df04c72d02e5aa62419540378e03fd1c36e78f` | no |
| `commands/lint.py` | `79f872896bee52c680d3f3367239a858639e4d9f021d152bc5831b74e487a9ce` | no |
| `commands/log_event.py` | `eab72464ff9aadee4f45285ebe99a698e9af321e2c3c1c6da4d6324993b47df7` | no |
| `commands/promote.py` | `43bb2ec6e7e431a9bbdda68abcf32c61a9fac285674edfa7746b2ec16794eef0` | no |
| `commands/register_summary.py` | `a518a09ea1b96969faa75d004c553fc7685092014a67f132203b07cc9d5b73e3` | no |
| `commands/reindex.py` | `35dbfa4a39980530b2b6c02d5ad460c68d6b2a38e2534051e63c4926c39a862a` | no |
| `commands/scan.py` | `d2d7b8889f4f724816d3fd45aa9a52fced98e206b18c9be46de985af092949bf` | no |
| `commands/update_index.py` | `95dcae27db01f35091709bd15e7b2133f17c8d6c4db02254dc02e85d189813b1` | no |
| `commands/upsert_page.py` | `e29c7e49097d4e71e77c72e1d7f8948c69b2dbbcd3d9028a723d7a08d9f6c815` | no |

## original_hashes (upstream snapshot — diff target for sync script)

These are the hashes from `Universal-skills/.../wiki_ingest/` at the synced commit. Only files
listed here that DIFFER from `file_hashes` above represent local divergence (and MUST have a
corresponding `local_patches[]` entry).

| path | sha256_upstream |
|---|---|
| `__init__.py` | `6e14184b350bc96ac34bd39ea7446fa1ea720463ad0c457817969e11622eeae3` |

_(other paths identical to `file_hashes` table — omitted to avoid duplication)_

## local_patches

> **Scope note** (extends Decision-12 of TASK 004 Meta): `local_patches[]` originally scoped
> to `mypy --strict` type-fixups (I-V.4). Bead 004-01 discovered that **vendoring infrastructure
> patches** (runtime shims required to make the package importable in a nested namespace) also
> belong in this block — they are deterministic, reversible, and the sync script's divergence
> check must be aware of them. Future TASK 004 / TASK 005 may amend the Decision-12 wording;
> for now `local_patches[]` covers BOTH type-fixups and infrastructure shims, each entry tagged
> by `kind`.

1. **path**: `__init__.py`
   - **kind**: `vendoring_shim` (not a mypy fix; see scope note above)
   - **reason**: Upstream uses absolute imports (`from wiki_ingest import _dispatch`) that
     work in standalone layout (sibling to `wiki_ops.py`) but break in nested namespace
     `scripts.wiki_ingest.*`. Patch registers the package under bare name `wiki_ingest` in
     `sys.modules` via `setdefault` — canonical vendoring pattern (mirrors
     `pip._vendor.__init__`).
   - **delta**: appended 3-line block at EOF; upstream content preserved verbatim above.
   - **upstream_issue**: TBD — should be filed against upstream to adopt relative imports
     (`from . import _dispatch`), which would remove the need for this shim. Until then,
     every sync MUST re-apply this patch.
   - **discovered_in**: bead 004-01 during Phase 2 verification;
     `from scripts.wiki_ingest.commands.ingest import execute` failed with
     `ModuleNotFoundError: wiki_ingest` until shim landed.
   - **upstream_sha256**: `6e14184b350bc96ac34bd39ea7446fa1ea720463ad0c457817969e11622eeae3`
   - **current_sha256**: `392171dfdef6adc2eb13349c9cdc2e8ec2ce29ada0b96d77924f5afedcd77575`
