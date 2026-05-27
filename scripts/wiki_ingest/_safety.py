"""F1 · Safety & I/O Primitives for the wiki-ingest skill.

Hardened layer for every fs-touching / user-input op: atomic + lock-
protected writes, `O_NOFOLLOW` capped reads, NFKC slugify, traversal-
rejecting `_safe_name`, markdown-aware `_safe_inline`, control-char +
length-capped `_safe_for_json`, symlink walk-filter, backport-safe
`_is_relative_to`, shared CLI-arg helper `_collect_names`, and the
`_LOG_FORBIDDEN_IN_DETAIL` deny-list regex. Stdlib-only; F1 root of the
dependency DAG. Contract locked by `../tests/test__safety.py`.
"""
from __future__ import annotations

import errno
import os
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

try:
    import fcntl  # POSIX only; advisory flock for concurrent-write safety
    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False


# Hard limits — refuse to read/write anything beyond these. Defensive against
# pathological vaults, hostile symlinks (e.g. /dev/zero), and OOM via
# attacker-supplied summary files.
MAX_PAGE_BYTES = 50 * 1024 * 1024       # 50 MiB per markdown file
MAX_SUMMARY_BYTES = 50 * 1024 * 1024    # 50 MiB for register-summary input
MAX_VALUE_BYTES = 2000                  # cap any scalar echoed into JSON output

# Exit-code matrix — see `references/exit_codes.md` for the authoritative
# audit + per-code call-site list. Codes 0/1/2 are inherited from TASK 015.
# Shipped 3..8 are TASK 015/016 numeric call sites (kept as magic numbers;
# the symbolic names live in references/exit_codes.md but the call sites
# are not refactored here — out-of-scope drive-by changes are prohibited).
# 10..19 reserved for future per-command extensions.
# 20..26 are the v1.1 contract band (NEW in TASK 017). Partial-success
# envelopes for codes 20/21/22/26 MUST carry a `phase` discriminator.
EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_USAGE = 2
EXIT_PARTIAL = 20
EXIT_SUBPROCESS = 21
EXIT_LLM = 22
EXIT_MISSING_VAULT_ID = 23
EXIT_INVALID_VAULT_ID = 24
EXIT_VAULT_ID_MISMATCH = 25
EXIT_TIMEOUT = 26


def die(msg: str, code: int = 1) -> None:
    """Print a `wiki_ops: error: <msg>` line to stderr and exit with `code`."""
    print(f"wiki_ops: error: {msg}", file=sys.stderr)
    sys.exit(code)


def slugify(text: str) -> str:
    """Unicode-aware slug. Preserves non-ASCII letters (Cyrillic, CJK, etc.).

    NFKC-normalizes the input first so that visually-identical Unicode
    code-point variants (composed vs decomposed, fullwidth vs ASCII)
    collapse onto the same slug — defense against confusable-character
    spoofing (S-M5).
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.strip().lower()
    # \w is Unicode-aware in Python 3 — keeps letters, digits, underscore;
    # collapses everything else into a single dash.
    text = re.sub(r"[^\w-]+", "-", text, flags=re.UNICODE)
    text = re.sub(r"-+", "-", text)
    return text.strip("-_")


_UNSAFE_NAME_RE = re.compile(r"[\x00-\x1f/\\\[\]|^]")


def _safe_name(name: str, kind: str = "name") -> str:
    """Validate that `name` is safe to use as a filename component.

    Rejects: empty, leading dot, path separators, traversal, control chars,
    markdown wiki-link metacharacters (`[`, `]`, `|`) that would break
    `[[name]]` round-trip, and template placeholders.
    NFKC-normalizes so that visually-identical Unicode variants are
    indistinguishable on disk (defense against confusable spoofing, S-M5).
    Returns the normalized name if safe; calls die() otherwise.
    """
    if not name or not name.strip():
        die(f"--{kind} is empty")
    name = unicodedata.normalize("NFKC", name).strip()
    if name in (".", "..") or name.startswith("."):
        die(f"--{kind}={name!r}: must not start with '.' or be a traversal token")
    if _UNSAFE_NAME_RE.search(name):
        die(f"--{kind}={name!r}: must not contain '/', '\\', control chars, "
            f"or markdown link metacharacters ('[', ']', '|', '^')")
    if ".." in name:
        die(f"--{kind}={name!r}: must not contain '..'")
    if "{{" in name or "}}" in name:
        die(f"--{kind}={name!r}: must not contain template placeholders '{{{{' or '}}}}'")
    if len(name) > 200:
        die(f"--{kind}: too long ({len(name)} chars; max 200)")
    return name


def _safe_inline(text: str, field: str) -> str:
    """Validate that `text` is safe to inline into a markdown page body.

    Rejects newlines (would break list-item rows), `## ` line-starts (would
    spoof real section headers), and standalone `---` lines (would spoof
    frontmatter or section separators).
    Returns trimmed text if safe; calls die() otherwise.
    """
    if text is None:
        return text
    s = text.strip("\n").rstrip()
    if "\r" in s or "\n" in s:
        die(f"--{field}: newlines are not allowed (would break markdown structure)")
    if s.lstrip().startswith("## "):
        die(f"--{field}: must not start with '## ' (would spoof a section header)")
    if s.lstrip().rstrip() == "---":
        die(f"--{field}: must not be a bare '---' (would spoof a separator)")
    return s


def _check_case_collision(target_dir: Path, name: str) -> str | None:
    """Return the existing filename if a casing/slug-equivalent file exists.

    Two-tier check:
    1. Pure case-collision (macOS APFS / Windows NTFS): `Foo.md` vs `foo.md`.
    2. Slug-collision (L-M1): `_Foo_.md`, `foo_bar.md`, `Foo`.md all reduce
       to slugs that overlap once `slugify()` is applied — register both and
       you've got two source rows for what's conceptually one entity.
       We flag the slug-collision separately so the operator can choose.

    Uses `os.scandir()` (P-L1) — at 10k+ files in `target_dir` this is
    ~3-5× cheaper than `Path.iterdir()` because scandir reuses the
    DirEntry's cached stat info.
    """
    if not target_dir.is_dir():
        return None
    want = (name + ".md").lower()
    want_slug = slugify(name)
    want_filename = name + ".md"
    with os.scandir(str(target_dir)) as it:
        for entry in it:
            entry_name = entry.name
            if entry_name.lower() == want and entry_name != want_filename:
                return entry_name
            # Slug-collision (only flag for non-identical filenames)
            existing_stem, dot, _ext = entry_name.rpartition(".")
            if not dot:
                existing_stem = entry_name
            if existing_stem == name:
                continue
            if want_slug and slugify(existing_stem) == want_slug:
                return entry_name
    return None


def _is_relative_to(child: Path, parent: Path) -> bool:
    """Path.is_relative_to backport-safe wrapper.

    Returns True iff `child.resolve()` is under `parent.resolve()`.
    Refuses to traverse beyond the intended parent (S-H1 containment).
    """
    try:
        return child.resolve().is_relative_to(parent.resolve())
    except AttributeError:  # Python < 3.9 — not expected, but harmless
        try:
            child.resolve().relative_to(parent.resolve())
            return True
        except ValueError:
            return False
    except (OSError, ValueError):
        return False


def _safe_open_for_read(path: Path, follow_symlink: bool = False) -> int | None:
    """Open `path` for reading without traversing a symlink, optionally.

    Returns an os-level file descriptor (caller must close), or None if `path`
    is missing. `follow_symlink=False` is the safe default — refuses to read a
    symlinked entry inside the vault, since following could exfiltrate
    arbitrary user files (~/.ssh/id_rsa, /etc/passwd, etc.).
    """
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW") and not follow_symlink:
        flags |= os.O_NOFOLLOW
    try:
        return os.open(str(path), flags)
    except FileNotFoundError:
        return None
    except OSError as e:
        if e.errno in (errno.ELOOP, errno.EMLINK) and not follow_symlink:
            # Symlink encountered with O_NOFOLLOW → treat as "skip"
            return None
        raise


def read_text(path: Path, *, follow_symlink: bool = False,
              max_bytes: int = MAX_PAGE_BYTES) -> str:
    """Read a vault file, refusing to traverse symlinks and capping size.

    Defends against:
    - symlink-follow exfiltration (HIGH-2 from security review)
    - unbounded read of /dev/zero or 4 GB log files (MED-3)
    Returns "" if the file does not exist OR is a symlink (with the symlink
    treated as missing — `_walk_pages` already skips them upstream).
    """
    fd = _safe_open_for_read(path, follow_symlink=follow_symlink)
    if fd is None:
        return ""
    try:
        # Stat via fd to avoid TOCTOU on the path
        st = os.fstat(fd)
        if st.st_size > max_bytes:
            die(f"refusing to read {path}: size {st.st_size} exceeds "
                f"MAX_PAGE_BYTES={max_bytes}", code=6)
        data = b""
        # Read up to max_bytes + 1 to detect growing files / pipes
        remaining = max_bytes + 1
        while remaining > 0:
            chunk = os.read(fd, min(remaining, 1 << 20))
            if not chunk:
                break
            data += chunk
            remaining -= len(chunk)
        if len(data) > max_bytes:
            die(f"refusing to read {path}: grew past MAX_PAGE_BYTES during read",
                code=6)
        return data.decode("utf-8", errors="replace")
    finally:
        os.close(fd)


def _atomic_write_text(path: Path, content: str) -> None:
    """Write `content` to `path` atomically: tmp-file + fsync + os.replace.

    Uses O_NOFOLLOW on the target directory to refuse if the parent itself is
    a symlink swap. The tmp-file is created in the same directory so
    os.replace is a same-filesystem rename. Defends against:
    - mid-write crash leaving truncated files
    - concurrent-writer last-writer-wins corruption (advisory flock)
    - symlink-swap-between-check-and-write TOCTOU (O_NOFOLLOW on tmp open)

    On `os.write` / `os.fsync` failure the tmp-file is unlinked before the
    exception propagates (M2-015-01 fix — previously the orphan tmp leaked
    into the parent directory on every crash).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent),
    )
    write_succeeded = False
    try:
        # Acquire advisory exclusive lock on the tmp fd; if a concurrent
        # writer holds the lock for the same target, we serialize.
        if _HAS_FCNTL:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
            except OSError:
                pass  # non-fatal — best-effort serialization
        os.write(fd, content.encode("utf-8"))
        os.fsync(fd)
        write_succeeded = True
    finally:
        os.close(fd)
        if not write_succeeded:
            # Clean up the orphan tmp file (M2-015-01). `missing_ok=True`
            # so a partial-create that never reached `mkstemp`'s return
            # path doesn't double-fault here.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    # os.replace is atomic within the same filesystem
    os.replace(tmp_path, path)


def write_text(path: Path, content: str, dry_run: bool) -> None:
    """Atomic write with dry-run support and symlink-overwrite refusal.

    The dry-run branch prints the would-be content to stdout (used by every
    mutating subcommand's `--dry-run` flag). The real-write branch enforces
    MAX_PAGE_BYTES and refuses to overwrite a symlink (which would write to
    the link's target, allowing escape from the vault root).
    """
    if dry_run:
        print(f"--- WOULD WRITE: {path} ---")
        print(content)
        print(f"--- END {path} ---")
        return
    if len(content.encode("utf-8")) > MAX_PAGE_BYTES:
        die(f"refusing to write {path}: content exceeds "
            f"MAX_PAGE_BYTES={MAX_PAGE_BYTES}", code=6)
    # Refuse to write through a symlink — if `path` is a symlink, follow it
    # and you write to the target the attacker chose. Replace via temp+rename
    # which collapses a symlink into a regular file at the original location
    # (os.replace replaces the link itself, not its target — desired here).
    if path.is_symlink():
        die(f"refusing to overwrite symlink: {path} → {os.readlink(path)}",
            code=7)
    _atomic_write_text(path, content)


_CTRL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _safe_for_json(value, *, max_bytes: int = MAX_VALUE_BYTES):
    """Sanitize a value before echoing into JSON output (S-M6).

    Strips C0 control characters (except tab 0x09 and LF 0x0a, which JSON
    escapes natively via `\\t` / `\\n`) and 0x7f DEL; truncates overly
    long strings. Recurses into lists/dicts. Prevents prompt-injection-
    via-frontmatter chains where an attacker-controlled `title:` or
    `concept:` value would otherwise land verbatim in the agent's
    planning context.

    Defense-in-depth caveat (vdd-multi 2026-05-27): this filter is the
    JSON-output safety net only. Structural rejection of newlines /
    pipes / log-heading-spoofs in user-supplied prose fields is the
    job of `_safe_inline` (called by atomic ops at their CLI boundary).
    `_safe_for_json` is intentionally lax on tab/LF because JSON's own
    escape mechanism handles them safely; upstream `_safe_inline`
    rejects them where they would corrupt log / index formats.
    """
    if isinstance(value, str):
        cleaned = _CTRL_CHARS_RE.sub("", value)
        if len(cleaned) > max_bytes:
            cleaned = cleaned[:max_bytes] + f"…[truncated, {len(cleaned)} chars total]"
        return cleaned
    if isinstance(value, list):
        return [_safe_for_json(v, max_bytes=max_bytes) for v in value]
    if isinstance(value, dict):
        return {k: _safe_for_json(v, max_bytes=max_bytes) for k, v in value.items()}
    return value


def _skip_symlink(p: Path) -> bool:
    """True if `p` is a symlink (and therefore unsafe to traverse).

    Used in directory walks to refuse silently to follow links out of the
    vault. We don't `die()` here because a malicious symlink in someone
    else's wiki shouldn't crash `lint`/`reindex` — just skip it.
    """
    try:
        return p.is_symlink()
    except OSError:
        return True  # be conservative on stat errors


def _collect_names(comma_arg: str | None, repeated_arg: list[str] | None) -> list[str]:
    """Combine `--new-X "a,b,c"` and repeated `--new-X-name "a"` into one list.

    Shared by `cmd_update_index` and `cmd_append_log` (and any future CLI
    subcommand needing comma-list + repeated-flag merging). Repeated args
    are safe for names containing commas; the comma-arg is back-compat
    only and should be used when names are guaranteed comma-free.
    Repeated args win on overlap.
    """
    out: list[str] = []
    seen: set[str] = set()
    for n in (repeated_arg or []):
        n = n.strip()
        if n and n not in seen:
            out.append(n); seen.add(n)
    if comma_arg:
        for n in comma_arg.split(","):
            n = n.strip()
            if n and n not in seen:
                out.append(n); seen.add(n)
    return out


# Shared deny-list regex for log-event detail strings: forbids newlines,
# carriage returns, and `^## [` (which would spoof a log heading and break
# the grep-friendly format). Used by `cmd_append_log` and `cmd_log_event`.
_LOG_FORBIDDEN_IN_DETAIL = re.compile(r"[\n\r]|^## \[")
