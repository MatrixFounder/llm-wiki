"""Phase 3a benchmark harness — synthetic vault generator + SLO latency runner
(task-001-33, R-14).

Generates synthetic vaults at N pages, exercises every Phase 3a operation,
measures per-op latency, and compares against SLO targets from TASK.md §5.1.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import tempfile
import time
from datetime import date, datetime
from pathlib import Path

from scripts.wiki_index.layout import (
    CONCEPTS_SUBDIR,
    SCHEMA_FILE,
    SOURCES_SUBDIR,
)
from typing import Any, Callable

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_delta, reindex_full
from scripts.wiki_index.rendering import render_index
from scripts.wiki_index.lint import run_all_checks
from scripts.wiki_index.sqlite_repository import SQLiteRepository

# SLO table from TASK.md §5.1 (milliseconds)
SLOS = {
    "wiki-search": {100: 30, 1000: 50, 10000: 100},
    "wiki-index-upsert": {100: 50, 1000: 100, 10000: 100},
    "wiki-index-render": {100: 200, 1000: 1000, 10000: 5000},
    "wiki-lint": {100: 500, 1000: 2000, 10000: 30000},
    "wiki-reindex-full": {100: 2000, 1000: 20000, 10000: 180000},
    "wiki-reindex-delta": {100: 100, 1000: 500, 10000: 2000},
}


def generate_synthetic_vault(
    target_dir: Path,
    vault_id: str,
    n_pages: int,
    *,
    with_wikilinks: bool = True,
    seed: int = 42,
) -> None:
    """Generate `<target_dir>/_sources/page-NNNN.md` plus a WIKI_SCHEMA.md.

    Deterministic for fixed `seed`.
    """
    rng = random.Random(seed)
    target_dir.mkdir(parents=True, exist_ok=True)
    sources = target_dir / SOURCES_SUBDIR
    sources.mkdir(exist_ok=True)
    concepts = target_dir / CONCEPTS_SUBDIR
    concepts.mkdir(exist_ok=True)
    (target_dir / SCHEMA_FILE).write_text(
        f"---\nvault_id: {vault_id}\nschema_version: '2.0'\n---\n"
        f"# {vault_id}\n\nSynthetic vault for benchmarking.\n"
    )

    # Seed a small concept pool to wikilink against.
    n_concepts = max(10, n_pages // 50)
    for i in range(n_concepts):
        (concepts / f"concept-{i:04d}.md").write_text(
            f"---\ntype: concept\ntitle: Concept {i}\n---\n"
            f"# Concept {i}\n\nSynthetic concept body.\n"
        )

    for i in range(n_pages):
        body_parts = [
            f"# Synthetic Page {i}", "",
            f"Body paragraph for page-{i:04d}. " * 4,
            "",
        ]
        if with_wikilinks:
            n_links = rng.randint(1, 3)
            for _ in range(n_links):
                target = rng.randint(0, n_concepts - 1)
                body_parts.append(f"See [[concept-{target:04d}]] for details.")
        body = "\n".join(body_parts) + "\n"
        fm = (
            "---\n"
            f"type: summary\n"
            f"title: Synthetic Page {i}\n"
            f"date: '2026-05-{(i % 28) + 1:02d}'\n"
            f"tags: [bench, synth, page-{i % 10}]\n"
            "---\n"
        )
        (sources / f"page-{i:04d}.md").write_text(fm + body)


def measure(
    op_name: str,
    callable_: Callable[[], Any],
    runs: int = 5,
) -> dict[str, Any]:
    """Execute `callable_` `runs` times; return latency stats in ms.

    For ``runs`` < 20 the p95 field falls back to ``max_ms`` (a fair
    upper-bound estimate) because the empirical 95th percentile is
    ill-defined on small samples. The ``runs`` field is always reported so
    callers can judge confidence.
    """
    timings_ms: list[float] = []
    for _ in range(runs):
        t0 = time.perf_counter()
        callable_()
        timings_ms.append((time.perf_counter() - t0) * 1000.0)
    timings_ms.sort()
    if runs >= 20:
        p95 = statistics.quantiles(timings_ms, n=20)[18]
    else:
        # Under-sampled: report worst observed as an honest upper bound.
        p95 = max(timings_ms)
    return {
        "op": op_name,
        "runs": runs,
        "min_ms": round(min(timings_ms), 3),
        "p50_ms": round(statistics.median(timings_ms), 3),
        "p95_ms": round(p95, 3),
        "max_ms": round(max(timings_ms), 3),
    }


def _check_slo(
    op: str, n_pages: int, p95_ms: float
) -> tuple[bool, float | None]:
    if op not in SLOS:
        return True, None
    bucket = SLOS[op].get(n_pages)
    if bucket is None:
        return True, None
    return p95_ms <= bucket, float(bucket)


def run_suite(n_pages: int, output_json_path: Path | None = None,
              enforce_slos: bool = False, seed: int = 42) -> bool:
    """Build synthetic vault, run six operations, return True if all SLOs pass.

    Uses a temp dir so each invocation is hermetic. ``seed`` propagates to the
    mutator RNG so two runs with the same seed exercise the same workload.
    """
    results: list[dict[str, Any]] = []
    all_pass = True
    mutator_rng = random.Random(seed ^ 0xBEEF)

    with tempfile.TemporaryDirectory() as tmp:
        vault_root = Path(tmp) / "vault"
        db_path = Path(tmp) / "bench.db"
        vault_id = "bench-vault"

        generate_synthetic_vault(vault_root, vault_id, n_pages, seed=seed)

        repo = SQLiteRepository(db_path)
        repo.apply_schema()
        repo.register_vault(Vault(
            vault_id=vault_id, name=vault_id, root_path=vault_root,
            schema_version="2.0", registered_at=datetime(2026, 5, 26),
        ))

        # reindex --full (also seeds the DB for subsequent ops)
        full = measure("wiki-reindex-full",
                       lambda: reindex_full(repo, vault_id), runs=1)
        results.append(full)

        # wiki-search
        search = measure(
            "wiki-search",
            lambda: repo.search_pages("synthetic", vaults=[vault_id]),
            runs=5,
        )
        results.append(search)

        # wiki-index-upsert (one fresh page mutation)
        new_page = vault_root / SOURCES_SUBDIR / "bench-mutator.md"
        from scripts.wiki_source.base import SourceItem
        from scripts.wiki_source.manual import ManualSourceAdapter
        from scripts.wiki_index.normalization import normalize_frontmatter
        from scripts.wiki_index.reindex import _build_page

        adapter = ManualSourceAdapter()

        def _upsert_once() -> None:
            new_page.write_text(
                "---\ntype: summary\ntitle: Mutator\n"
                f"date: '2026-05-26'\ntags: [bench]\n---\n"
                f"# Mutator {mutator_rng.random()}\n"
            )
            item = SourceItem(kind="manual", source_path=new_page,
                              vault_root=vault_root, vault_id=vault_id)
            out = adapter.fetch(item)
            updated_fm, db_type = normalize_frontmatter(out.frontmatter)
            page = _build_page(out, vault_id, db_type, new_page, vault_root,
                               updated_fm)
            repo.upsert_page(page)

        upsert = measure("wiki-index-upsert", _upsert_once, runs=5)
        results.append(upsert)

        # wiki-index-render
        render = measure(
            "wiki-index-render",
            lambda: render_index(repo, vault_id),
            runs=3,
        )
        results.append(render)

        # wiki-lint
        lint = measure(
            "wiki-lint",
            lambda: run_all_checks(repo, vaults=[vault_id]),
            runs=3,
        )
        results.append(lint)

        # wiki-reindex --delta (no changes)
        delta = measure(
            "wiki-reindex-delta",
            lambda: reindex_delta(repo, vault_id),
            runs=3,
        )
        results.append(delta)

        repo.close()

    # SLO comparison
    for r in results:
        ok, target = _check_slo(r["op"], n_pages, r["p95_ms"])
        r["slo_target_ms"] = target
        r["slo_ok"] = ok
        if not ok:
            all_pass = False

    payload = {
        "n_pages": n_pages,
        "results": results,
        "all_pass": all_pass,
        "enforce_slos": enforce_slos,
    }
    json_out = json.dumps(payload, indent=2)
    if output_json_path:
        output_json_path.write_text(json_out)
    print(json_out)
    return all_pass or not enforce_slos


def run_multivault_scaling(
    n_vaults: int, pages_per_vault: int,
    output_json_path: Path | None = None,
) -> bool:
    """Generate N vaults, run cross-vault search + lint duplicates."""
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "multi.db"
        repo = SQLiteRepository(db_path)
        repo.apply_schema()
        vault_ids: list[str] = []
        for i in range(n_vaults):
            vid = f"bench-vault-{i:03d}"
            vault_ids.append(vid)
            vroot = Path(tmp) / vid
            generate_synthetic_vault(vroot, vid, pages_per_vault, seed=42 + i)
            repo.register_vault(Vault(
                vault_id=vid, name=vid, root_path=vroot,
                schema_version="2.0", registered_at=datetime(2026, 5, 26),
            ))
            reindex_full(repo, vid)

        cross_search = measure(
            "wiki-search-cross-vault",
            lambda: repo.search_pages("synthetic", vaults=vault_ids),
            runs=5,
        )
        results.append(cross_search)

        cross_dup = measure(
            "wiki-lint-cross-vault-dup",
            lambda: repo.find_cross_vault_concept_duplicates(),
            runs=3,
        )
        results.append(cross_dup)
        repo.close()

    payload = {
        "mode": "multivault-scaling",
        "n_vaults": n_vaults,
        "pages_per_vault": pages_per_vault,
        "results": results,
    }
    json_out = json.dumps(payload, indent=2)
    if output_json_path:
        output_json_path.write_text(json_out)
    print(json_out)
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Phase 3a benchmark harness")
    p.add_argument("--n", type=int, default=100,
                   help="Pages in single-vault suite (default 100)")
    p.add_argument("--multivault", nargs=2, type=int, metavar=("N", "M"),
                   help="Run multi-vault scaling: N vaults × M pages each")
    p.add_argument("--output", type=Path, help="Write JSON to this path too")
    p.add_argument("--enforce-slos", action="store_true",
                   help="Exit 1 if any SLO miss")
    args = p.parse_args(argv)

    if args.multivault:
        run_multivault_scaling(args.multivault[0], args.multivault[1],
                               args.output)
        return 0
    ok = run_suite(args.n, args.output, enforce_slos=args.enforce_slos)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
