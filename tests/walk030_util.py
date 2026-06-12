"""TASK 030 (bead 030-00) — walk instrumentation + synthetic-vault builders.

Shared by: the 030-00 baseline capture (docs/benchmarks/030-walk-baseline.md),
the 030-00 semantic pins, and the 030-05 AC-3.3 traversal-count tests.

NOT a test module (no test_* functions). Lives in tests/ — instrumentation must
never ship under scripts/ (bead 030-00 acceptance).
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


@contextmanager
def count_scandirs() -> Iterator[Counter[str]]:
    """Intercept `os.scandir` and count invocations per directory path.

    pathlib's 3.13+ globber (`glob._StringGlobber.scandir`) calls `os.scandir`
    at call time, so a module-level monkeypatch observes every directory
    enumeration the walk performs.

    KEY CONTRACT (Sarcasmotron 030-00 MED-1): keys are
    `os.path.normpath(os.fspath(path))` — the trailing separator the globber
    appends is STRIPPED, but the spelling is otherwise the CALLER's (NOT
    resolved: on macOS `/var/...` vs `/private/var/...` aliases stay distinct).
    NEVER assert `counts[str(d)] == 0` directly — a spelling mismatch passes
    vacuously. Use `count_for(counts, d)` which compares RESOLVED paths.
    """
    counts: Counter[str] = Counter()
    real_scandir = os.scandir

    def spy(path: Any = None) -> Any:
        if path is None:                      # os.scandir(None) ≡ os.scandir('.')
            counts[os.path.normpath(".")] += 1
            return real_scandir()
        if isinstance(path, int):             # fd-based scandir: pass through
            counts[f"<fd:{path}>"] += 1
            return real_scandir(path)
        counts[os.path.normpath(os.fspath(path))] += 1
        return real_scandir(path)

    os.scandir = spy  # type: ignore[assignment]
    try:
        yield counts
    finally:
        os.scandir = real_scandir  # type: ignore[assignment]


@contextmanager
def count_direntry_stats() -> Iterator[Counter[str]]:
    """Count `DirEntry.stat()` calls per entry path (Sarcasmotron 030-05 HIGH:
    `os.DirEntry` is a C type whose methods cannot be monkeypatched — so the
    spy wraps `os.scandir` and yields Python PROXIES exposing the five members
    the walk uses; `.stat()` increments the counter, everything else forwards).
    Keys follow the count_scandirs normpath contract — use `count_for`."""
    counts: Counter[str] = Counter()
    real_scandir = os.scandir

    class _Proxy:
        __slots__ = ("_d",)

        def __init__(self, d: Any) -> None:
            self._d = d

        @property
        def name(self) -> str:
            return str(self._d.name)

        @property
        def path(self) -> str:
            return str(self._d.path)

        def is_dir(self, *, follow_symlinks: bool = True) -> bool:
            return bool(self._d.is_dir(follow_symlinks=follow_symlinks))

        def is_symlink(self) -> bool:
            return bool(self._d.is_symlink())

        def stat(self, *, follow_symlinks: bool = True) -> os.stat_result:
            counts[os.path.normpath(self._d.path)] += 1
            result: os.stat_result = self._d.stat(follow_symlinks=follow_symlinks)
            return result

    class _It:
        def __init__(self, it: Any) -> None:
            self._it = it

        def __enter__(self) -> "_It":
            return self

        def __exit__(self, *a: Any) -> None:
            self._it.close()

        def __iter__(self) -> "_It":
            return self

        def __next__(self) -> _Proxy:
            return _Proxy(next(self._it))

        def close(self) -> None:
            self._it.close()

    def spy(path: Any = None) -> Any:
        return _It(real_scandir(path) if path is not None else real_scandir())

    os.scandir = spy  # type: ignore[assignment]
    try:
        yield counts
    finally:
        os.scandir = real_scandir  # type: ignore[assignment]


def count_for(counts: Counter[str], directory: Path) -> int:
    """Total scandir calls for `directory`, comparing RESOLVED paths (immune to
    the /var↔/private/var alias and any caller-spelling drift). O(len(counts))
    — fine for tests. This is the ONLY supported lookup for zero/exact-count
    assertions (see the count_scandirs key contract)."""
    target = Path(directory).resolve()
    total = 0
    for key, n in counts.items():
        if key.startswith("<fd:"):
            continue
        if Path(key).resolve() == target:
            total += n
    return total


def _write(root: Path, rel: str, body: str = "# stub\n\ntext\n") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def build_para_vault(
    root: Path, *, areas: int = 8, subs: int = 6, files_per_sub: int = 42
) -> int:
    """obsidian-personal-shaped synthetic vault (PARA): numbered areas with
    subdirs, underscore system dirs, one root-level MOC per area, planted
    ignored subtrees (`_raw`, `.obsidian`). Defaults yield >= 2k md files
    (8*6*42 = 2016 + extras) — the R-X1-OBS-WALK measurement scale.

    Returns the number of INDEXABLE .md files written (ignored trees excluded).
    """
    n = 0
    for d in ("_daily/2026", "_clippings", "_inbox"):
        for i in range(20):
            _write(root, f"{d}/note-{i:03d}.md")
            n += 1
    for a in range(areas):
        area = f"{a:02d} - Area{a}"
        _write(root, f"{area}.md")  # root-level MOC (entry-6/entry-7 overlap)
        n += 1
        for s in range(subs):
            for f in range(files_per_sub):
                _write(root, f"{area}/Sub{s}/note-{f:03d}.md")
                n += 1
        # planted ignored subtree under the first sub (`**/_raw/**`)
        for f in range(10):
            _write(root, f"{area}/Sub0/_raw/raw-{f:02d}.md")
    # planted root-level ignored trees
    for f in range(25):
        _write(root, f".obsidian/plugins/cache-{f:02d}.md")
        _write(root, f"_templates/tpl-{f:02d}.md")
    return n


def build_fat_karpathy_vault(root: Path, *, pages: int = 60, fat: int = 200) -> int:
    """karpathy-shaped vault + FAT non-page subtrees (`.obsidian/`, `.git/`,
    `attachments/`) that the per-glob engine never walks today (the §3.5 "root
    subtrees never walked" property — AC-3.3(ii) fixture).

    Returns the number of indexable .md files written.
    """
    n = 0
    for i in range(pages):
        _write(root, f"_sources/src-{i:03d}.md",
               f"---\ntype: summary\ntitle: S{i}\n---\n\nbody {i}\n")
        n += 1
    for i in range(pages // 3):
        _write(root, f"_concepts/c-{i:03d}.md",
               f"---\ntype: concept\ntitle: C{i}\n---\n\nbody\n")
        n += 1
    for i in range(pages // 2):
        _write(root, f"Lessons/Course-X/_sources/l-{i:03d}.md",
               f"---\ntype: summary\ntitle: L{i}\n---\n\nbody\n")
        n += 1
    for f in range(fat):
        _write(root, f".obsidian/workspace/json-{f:03d}.md")
        _write(root, f".git/objects/aa/blob-{f:03d}.md")
        _write(root, f"attachments/deep/nest/img-{f:03d}.md")
    return n
