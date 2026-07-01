"""`wiki-init` CLI — scaffold-new / register-existing / reconcile.

Real impl per tasks 001-21/22/23.

Exit codes:
  0 — success
  1 — usage error
  2 — INVALID_VENDOR / INDEX_DB_ALREADY_DECLARED (TASK 022)
  6 — MISSING_WIKI_SCHEMA / MISSING_VAULT_ID / INVALID_VAULT_ID /
      VAULT_ID_COLLISION / VAULT_NOT_REGISTERED / VAULT_NOT_FOUND /
      INVALID_INDEX_DB (TASK 022/025 — unified to exit 6, field `index_db`,
      matching the centralized _common.build_repo_config emitter)
  7 — VAULT_RENAMED warning; requires --confirm to apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any

import yaml

from scripts.wiki_index.config_loader import (
    ConfigValidationError,
    validate_index_db_value,
)
from scripts.wiki_index.factory import make_repo
from scripts.wiki_skills._common import atomic_write_text, build_repo_config
from scripts.wiki_index.layout import (
    COURSE_TIER_DIR,
    LOG_SUBDIR,
    SCAFFOLD_DIRS,
    SCHEMA_FILE,
    VAULT_INDEX_DIR,
)
from scripts.wiki_index.layout_config import is_two_tier_scaffold, layout_choices
from scripts.wiki_index.models import LogEvent, Vault

_VAULT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}[a-z0-9]$")
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"

# TASK 031 / R-031-3: the `--layout` choice-set, the legacy aliases
# (`flat`/`per-project`→karpathy), and the two-tier-scaffold family are SOURCED
# from the built-in `layouts/*.yaml` registry (layout_config.layout_choices() /
# is_two_tier_scaffold()) — no hardcoded list lives here anymore. A new layout is
# a pure drop-in YAML (declaring optional `aliases`/`init_scaffold`) with zero edits.


def _validate_vault_id(vault_id: str) -> bool:
    if vault_id == "_global_":
        return True
    return bool(_VAULT_ID_RE.match(vault_id)) and "--" not in vault_id


def _emit(payload: dict[str, Any], exit_code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return exit_code


def _split_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---\n"):
        return {}
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return {}
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}
    return fm if isinstance(fm, dict) else {}


def _suggested_vault_id(vault_root: Path) -> str:
    base = vault_root.name.lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base or "my-vault"


def _sanitize_desc(desc: str | None, vault_id: str) -> str:
    """Description for the templates' double-quoted YAML scalar (DF-3): drop the
    `"`/newlines that would break the quoted scalar (and thus the §D8
    rebuild-from-Class-A path)."""
    d = desc or f"LLM Wiki vault: {vault_id}"
    return d.replace('"', "'").replace("\n", " ").replace("\r", " ")


_AGENT_FILES_CONFIG = _TEMPLATES_DIR / "agent-files.yaml"


def _load_vendor_config() -> tuple[
    dict[str, tuple[str, str]], list[str], dict[str, tuple[str, str]]
]:
    """``({vendor: (filename, template_name)}, default_vendors, {vendor:
    (settings_file, settings_template)})`` from ``templates/agent-files.yaml``
    (CLAUDE.md/Claude Code, GEMINI.md/Gemini CLI, …). The third map is the optional
    per-vendor settings file (TASK 026 — only vendors that declare both
    ``settings_file`` + ``settings_template``; e.g. claude → ``.claude/settings.json``).
    Falls back to Claude-only (incl. its settings) if the config is missing/malformed,
    so a vault always gets at least a CLAUDE.md."""
    fallback: tuple[dict[str, tuple[str, str]], list[str], dict[str, tuple[str, str]]] = (
        {"claude": ("CLAUDE.md", "CLAUDE.md.tmpl")}, ["claude"],
        {"claude": (".claude/settings.json", "vault.claude-settings.json")},
    )
    try:
        doc = yaml.safe_load(_AGENT_FILES_CONFIG.read_text(encoding="utf-8"))
        vendors = {
            str(k): (str(v["filename"]), str(v["template"]))
            for k, v in doc["vendors"].items()
        }
        settings = {
            str(k): (str(v["settings_file"]), str(v["settings_template"]))
            for k, v in doc["vendors"].items()
            if v.get("settings_file") and v.get("settings_template")
        }
        default = [str(x) for x in (doc.get("default_vendors") or list(vendors))]
        return (vendors or fallback[0], default or fallback[1], settings)
    except Exception:  # noqa: BLE001 — trusted repo file; any fault → safe default
        return fallback


def _resolve_vendors(
    arg: str | None, vendors: dict[str, tuple[str, str]], default: list[str]
) -> tuple[list[str], list[str]]:
    """Resolve the ``--vendor`` selection → ``(selected, unknown)``. ``None`` →
    `default` (one vendor — CLAUDE.md); ``"all"`` → every configured vendor;
    else a comma-separated list. ``unknown`` lists any name not in the config."""
    if not arg or not arg.strip():
        selected = list(default)
    elif arg.strip().lower() == "all":
        selected = list(vendors)
    else:
        selected = [v.strip() for v in arg.split(",") if v.strip()]
    unknown = [v for v in selected if v not in vendors]
    return selected, unknown


def _write_agent_files(
    vault_root: Path, placeholders: dict[str, str],
    vendors: dict[str, tuple[str, str]], selection: list[str],
    settings: dict[str, tuple[str, str]] | None = None, *, force: bool,
) -> dict[str, str]:
    """Render the agent-instructions file for each SELECTED vendor into the vault
    root (default: CLAUDE.md only; `--vendor` picks others/all) so an agent
    launched there gets the wiki operating instructions. NON-destructive: writes
    each only if absent (or ``--force``) — never clobbers an operator's own file.
    TASK 026: also drops the vendor's settings file (e.g. claude →
    `.claude/settings.json`) if it declares one — copied VERBATIM (it is JSON with a
    `$schema`, so NOT a `string.Template`) and INDEPENDENTLY of the agent file (so an
    existing CLAUDE.md does not skip the settings write); equally non-destructive.
    Returns ``{relpath: "written"|"exists"|"error"}``. Shared by `scaffold_new`
    and `register_existing` (a registered vault is otherwise agent-unusable —
    DF-018-INIT-1)."""
    settings = settings or {}
    out: dict[str, str] = {}
    for vendor in selection:
        filename, template_name = vendors[vendor]
        # TASK 025 / R-5: the default vendor template (CLAUDE.md.tmpl) is Karpathy-centric
        # (three-layer _sources/_concepts/_entities, promote/demote, a Lessons/ diagram) —
        # wrong for an existing-tree layout. For dev-project / obsidian-personal select the
        # layout-aware template instead, for EVERY selected vendor (the switch is
        # layout-driven, not vendor-driven; the layout template's placeholders are a subset
        # of the Karpathy one's, so .substitute below stays well-formed).
        # NB (vdd-multi logic LOW): today every vendor maps to CLAUDE.md.tmpl, so this
        # single override is correct. If a future vendor-specific template is added
        # (e.g. GEMINI.md.tmpl per templates/agent-files.yaml), make this layout-suffix
        # aware (derive "<base>.layout.md.tmpl") so a non-Karpathy vendor keeps its own
        # template rather than silently reverting to the Claude layout file.
        if not is_two_tier_scaffold(placeholders.get("layout") or ""):
            template_name = "CLAUDE.layout.md.tmpl"
        target = vault_root / filename
        if filename in out:
            # TASK 043: two selected vendors share a filename (e.g. `agents` + `pi` both
            # write AGENTS.md under `--vendor all`). The first already rendered it this run —
            # don't re-render (it would downgrade the status to "exists"); fall through to the
            # settings block so a same-file vendor's settings (pi's permissions.json) still land.
            pass
        elif target.exists() and not force:
            out[filename] = "exists"
        else:
            # Per-vendor resilience: a missing/misconfigured template (or a stray `$`
            # in it) must NOT crash init — the vault is already registered and the
            # other vendors' files are unaffected (vdd-adversarial).
            try:
                rendered = Template(
                    (_TEMPLATES_DIR / template_name).read_text(encoding="utf-8")
                ).substitute(placeholders)
            except (OSError, KeyError, ValueError):
                out[filename] = "error"
            else:
                target.write_text(rendered)
                out[filename] = "written"
        # TASK 026: also drop the vendor's settings file (e.g. .claude/settings.json),
        # INDEPENDENTLY of the agent file above (an existing CLAUDE.md must not skip it).
        # VERBATIM copy — the JSON carries a `$schema`, so NEVER Template.substitute it.
        if vendor in settings:
            s_file, s_tmpl = settings[vendor]
            # vdd-multi security LOW (CWE-22, defense-in-depth): settings_file comes from
            # the trusted agent-files.yaml, but containment is cheap insurance — an
            # absolute or `..`-bearing value would escape the vault (an absolute RHS makes
            # `vault_root / s_file` discard vault_root). Mirror the _validate_index_db_rel
            # posture: refuse anything not vault-relative.
            s_rel = Path(s_file)
            if s_rel.is_absolute() or ".." in s_rel.parts:
                out[s_file] = "error"
                continue
            s_target = vault_root / s_rel
            if s_target.exists() and not force:
                out[s_file] = "exists"  # never clobber an operator's accumulated rules
            else:
                try:
                    content = (_TEMPLATES_DIR / s_tmpl).read_text(encoding="utf-8")
                    s_target.parent.mkdir(parents=True, exist_ok=True)
                    atomic_write_text(s_target, content)
                except OSError:  # template unreadable OR write fault (RO dir/ENOSPC) —
                    out[s_file] = "error"  # non-fatal: the vault is already registered
                else:
                    out[s_file] = "written"
    return out


def _write_page_type_templates(
    vault_root: Path, layout: str, *, force: bool,
) -> dict[str, str]:
    """Copy the per-class page-type scaffolds (`templates/page-types/*.md`) into
    ``<vault>/.wiki/page-types/`` for **existing-tree (non-two-tier) layouts**
    (`cybos` / `dev-project` / `obsidian-personal`), so an agent launched IN the vault
    — and the human in Obsidian — has the typed-knowledge authoring templates LOCALLY;
    they otherwise live only in the obsidian-llm-wiki repo, invisible to a vault-only
    agent. The Karpathy family (`karpathy`/`flat`/`per-project`) uses the
    concept/entity model, not typed classes → no copy.

    VERBATIM copy — the page-type templates use ``<placeholder>`` literals, NOT
    ``string.Template`` (so a stray ``$`` would not raise; copying byte-for-byte also
    preserves the literal ``${...}``-free frontmatter). Per-file **non-destructive**
    (an edited scaffold is never clobbered without ``--force``). The target lives under
    ``.wiki/``, which the index walk prunes (dot-directory — verified) and which
    `file_extensions: ['.md']` would NOT otherwise exclude, so this is the safe home:
    the copies are **never indexed as junk pages**. Returns ``{relpath: "written" |
    "exists" | "error"}`` (empty for the Karpathy family)."""
    out: dict[str, str] = {}
    if is_two_tier_scaffold(layout):
        return out  # Karpathy family — typed knowledge classes are N/A
    src_dir = _TEMPLATES_DIR / "page-types"
    dest_dir = vault_root / ".wiki" / "page-types"
    try:
        srcs = sorted(src_dir.glob("*.md"))
    except OSError:
        return out
    for src in srcs:
        rel = f".wiki/page-types/{src.name}"
        target = dest_dir / src.name
        if target.exists() and not force:
            out[rel] = "exists"
            continue
        try:
            content = src.read_text(encoding="utf-8")
            dest_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_text(target, content)
        except OSError:  # unreadable source OR write fault — non-fatal (vault is registered)
            out[rel] = "error"
        else:
            out[rel] = "written"
    return out


def _index_db_value(args: argparse.Namespace) -> str | None:
    """TASK 022 — the index_db to declare: ``--index-db`` wins; ``--local`` ⇒
    ``.wiki/index.db``; else ``None`` (global DB, unchanged)."""
    if getattr(args, "index_db", None):
        return str(args.index_db)
    if getattr(args, "local", False):
        return ".wiki/index.db"
    return None


def _validate_index_db_rel(rel: str) -> bool:
    """vdd-multi MED-S1 (frontmatter injection): an `index_db` written into the YAML
    frontmatter must be a single, clean scalar. Reject empty / surrounding whitespace /
    a `---` fence / and **any** character that is whitespace except a literal space or
    tab — this bans not only `\\n`/`\\r` but the **Unicode line separators U+0085 (NEL),
    U+2028, U+2029** that PyYAML treats as line breaks (an interior one survives
    `.strip()` and would inject a sibling key, e.g. `vault_id`, overriding vault
    identity — vdd-multi MED-S1 round-2 PoC) — plus NUL / control / DEL chars."""
    # `": "` is the YAML block-mapping indicator: a value like `a: b` would write
    # invalid frontmatter (`index_db: a: b`) → corrupt the Class-A file + an uncaught
    # parse error on the next read (vdd-multi round-3 self-DoS note). No real path
    # contains a colon-space, so banning it is safe.
    if not rel or rel != rel.strip() or "---" in rel or ": " in rel:
        return False
    return all(
        ch in " \t" or (not ch.isspace() and ord(ch) >= 0x20 and ord(ch) != 0x7f)
        for ch in rel
    )


def _ensure_index_db(schema_path: Path, rel: str) -> str:
    """Declare ``index_db: <rel>`` in the WIKI_SCHEMA.md frontmatter.

    Returns ``"written"`` (inserted), ``"unchanged"`` (already declared == rel), or
    ``"conflict"`` (already declared a DIFFERENT value — vdd-multi MED-L2: do NOT
    silently honour the stale value). Fence-aware (splits on the `---\\n` frontmatter
    fence, NOT a `find` that could match `---` inside a block scalar — vdd-multi LOW)
    and **atomic** (`atomic_write_text`, never a torn Class-A file)."""
    text = schema_path.read_text(encoding="utf-8")
    fm = _split_frontmatter(text)
    existing = fm.get("index_db") if isinstance(fm, dict) else None
    if existing:
        return "unchanged" if str(existing) == rel else "conflict"
    parts = text.split("---\n", 2)  # ['', <frontmatter>, <body>]
    if not text.startswith("---\n") or len(parts) < 3:
        return "written"  # no parseable frontmatter — caller already validated vault_id
    new_text = ("---\n" + parts[1].rstrip("\n") + f"\nindex_db: {rel}\n---\n" + parts[2])
    atomic_write_text(schema_path, new_text)
    return "written"


def scaffold_new(args: argparse.Namespace) -> int:
    # Require --vault explicitly. Silently defaulting to cwd ("." ) has
    # caused accidental scaffolds inside the project repo. Operator must
    # opt in to the target directory.
    if not args.vault:
        return _emit({
            "error": "MISSING_VAULT_ARG",
            "hint": "provide --vault <absolute path> (cwd default removed "
                    "to prevent accidental scaffolds in the project repo)",
        }, exit_code=1)
    vault_id = args.vault_id or _suggested_vault_id(Path(args.vault))
    if not _validate_vault_id(vault_id):
        return _emit({"error": "INVALID_VAULT_ID", "received": vault_id,
                      "pattern": _VAULT_ID_RE.pattern}, exit_code=6)
    # Resolve --vendor FAIL-FAST — before any dir/schema write, so a typo'd
    # vendor leaves no partial scaffold (vdd-adversarial).
    _vendors, _default_vendors, _vendor_settings = _load_vendor_config()
    _selection, _unknown = _resolve_vendors(args.vendor, _vendors, _default_vendors)
    if _unknown:
        return _emit({"error": "INVALID_VENDOR", "unknown": _unknown,
                      "known": sorted(_vendors)}, exit_code=2)
    vault_root = Path(args.vault).resolve()
    vault_root.mkdir(parents=True, exist_ok=True)
    # TASK 012 / R-X2.1: only the Karpathy family gets the two-tier page-subdir
    # scaffold (_sources/_concepts/…). dev-project / obsidian-personal index an
    # EXISTING tree (docs/, numbered folders), so scaffolding Karpathy dirs into
    # a real repo would be wrong — write WIKI_SCHEMA.md + register only.
    _layout = args.layout or "per-project"
    # TASK 040 / ADR-007 audit: this is NOT a layout-NAME fork — the gate is the config-driven
    # `is_two_tier_scaffold` registry flag (TASK 031), and SCAFFOLD_DIRS is the two-tier scaffold's
    # page-subdir set. Any two-tier-scaffold layout (not only karpathy) qualifies; left as-is
    # (the grep fork-guard does not flag it). `_karpathy` is a legacy var name for that flag.
    _karpathy = is_two_tier_scaffold(_layout)
    if _karpathy:
        for sub in SCAFFOLD_DIRS:
            (vault_root / sub).mkdir(parents=True, exist_ok=True)
    # DF-3 (dogfood): the description renders into a *double-quoted* YAML scalar
    # in the template (`description: "${description}"`). The old default
    # `LLM Wiki vault: {vault_id}` had an unquoted colon → invalid YAML →
    # MISSING_VAULT_ID on --register-existing (the §D8 rebuild-from-Class-A
    # path). Quoting fixes the colon; sanitize embedded `"`/newlines so the
    # quoted scalar stays well-formed even for an operator-supplied --description.
    _desc = _sanitize_desc(args.description, vault_id)
    placeholders = {
        "vault_id": vault_id,
        "language": args.language or "en",
        "layout": _layout,
        "description": _desc,
    }
    schema_path = vault_root / SCHEMA_FILE
    if not schema_path.exists() or args.force:
        schema_path.write_text(
            Template((_TEMPLATES_DIR / "WIKI_SCHEMA.md.tmpl").read_text())
            .substitute(placeholders)
        )
    # TASK 022: declare a vault-local index_db (--local / --index-db) in WIKI_SCHEMA.md.
    _idx = _index_db_value(args)
    if _idx:
        if not _validate_index_db_rel(_idx):
            return _emit({"error": "INVALID_INDEX_DB", "field": "index_db",
                          "reason": "must be a single-line path (no newline/NUL/---)"},
                         exit_code=6)
        # TASK 025 / R-1: validate path-safety (absolute→WIKI_ALLOW_ABSOLUTE_INDEX_DB
        # gate, symlink, escape, NUL) BEFORE _ensure_index_db writes, so a rejected
        # index_db never leaves a half-applied Class-A mutation. `_idx` is already
        # edge-whitespace-free (the _validate_index_db_rel check above).
        try:
            validate_index_db_value(_idx, vault_root)
        except ConfigValidationError:
            return _emit({"error": "INVALID_INDEX_DB", "field": "index_db",
                          "reason": "index_db is unsafe or malformed (escapes the vault, "
                                    "is a symlink, or is an absolute path outside the "
                                    "framework's app-data dir without "
                                    "WIKI_ALLOW_ABSOLUTE_INDEX_DB)",
                          "hint": "An absolute index_db under the OS app-data dir "
                                  "(…/Application Support, …/.local/share, %APPDATA%) is "
                                  "trusted automatically; any other absolute path requires "
                                  "WIKI_ALLOW_ABSOLUTE_INDEX_DB=1."},
                         exit_code=6)
        if _ensure_index_db(schema_path, _idx) == "conflict":
            return _emit({"error": "INDEX_DB_ALREADY_DECLARED", "field": "index_db",
                          "reason": "WIKI_SCHEMA.md already declares a different index_db"},
                         exit_code=2)
    agent_files = _write_agent_files(
        vault_root, placeholders, _vendors, _selection, _vendor_settings,
        force=bool(args.force))
    page_type_templates = _write_page_type_templates(
        vault_root, placeholders["layout"], force=bool(args.force))
    if _karpathy:
        idx = vault_root / VAULT_INDEX_DIR / "index.md"
        if not idx.exists():
            idx.write_text(f"# {vault_id} Index\n\nAuto-generated.\n")
        now = datetime.now()
        log_month = (vault_root / VAULT_INDEX_DIR / LOG_SUBDIR /
                     f"{now.strftime('%Y-%m')}.md")
        if not log_month.exists():
            log_month.write_text(f"# Log {now.strftime('%Y-%m')}\n\n")

    config = build_repo_config(  # TASK 022: index_db (if declared) → local DB
        vault_id, vault_root=vault_root,
        db_path_flag=str(args.db_path) if args.db_path else None)
    repo = make_repo(config)
    db_path = getattr(repo, "db_path", None)
    try:
        if repo.get_vault(vault_id) is None:
            repo.register_vault(Vault(
                vault_id=vault_id,
                name=placeholders["description"],
                root_path=vault_root,
                schema_version="2.0",
                registered_at=datetime.now(),
                config_json={"language": placeholders["language"],
                             "layout": placeholders["layout"]},
            ))
    finally:
        repo.close()
    return _emit({
        "action": "scaffolded",
        "vault_id": vault_id,
        "vault_root": str(vault_root),
        "db_path": str(db_path),
        "agent_files": agent_files,
        "page_type_templates": page_type_templates,
    })


def register_existing(args: argparse.Namespace) -> int:
    if not args.vault:
        return _emit({"error": "MISSING_VAULT_ARG",
                      "hint": "provide --vault <path>"}, exit_code=1)
    try:
        vault_root = Path(args.vault).resolve(strict=True)
    except FileNotFoundError:
        return _emit({"error": "VAULT_NOT_FOUND", "vault": str(args.vault)},
                     exit_code=6)
    schema_path = vault_root / SCHEMA_FILE
    if not schema_path.is_file():
        return _emit({
            "error": "MISSING_WIKI_SCHEMA",
            "expected_path": str(schema_path),
            "hint": "Run wiki-init --scaffold-new (or --register-existing) to create WIKI_SCHEMA.md",
        }, exit_code=6)
    fm = _split_frontmatter(schema_path.read_text(encoding="utf-8"))
    vault_id = fm.get("vault_id")
    if not vault_id:
        return _emit({
            "error": "MISSING_VAULT_ID",
            "wiki_schema_path": str(schema_path),
            "suggested_vault_id": _suggested_vault_id(vault_root),
            "hint": "Add 'vault_id: <slug>' to WIKI_SCHEMA.md frontmatter "
                    "(ADR-002 §D1.1, no hash fallback).",
        }, exit_code=6)
    if not _validate_vault_id(vault_id):
        return _emit({
            "error": "INVALID_VAULT_ID",
            "received": vault_id,
            "pattern": _VAULT_ID_RE.pattern,
        }, exit_code=6)
    # Resolve --vendor FAIL-FAST — before registering, so a typo'd vendor never
    # leaves a registered-but-errored state (vdd-adversarial).
    vendors, default_vendors, vendor_settings = _load_vendor_config()
    selection, unknown = _resolve_vendors(args.vendor, vendors, default_vendors)
    if unknown:
        return _emit({"error": "INVALID_VENDOR", "unknown": unknown,
                      "known": sorted(vendors)}, exit_code=2)
    is_two_tier = any((vault_root / COURSE_TIER_DIR).glob(f"*/{SCHEMA_FILE}"))
    # TASK 022: declare a vault-local index_db (--local / --index-db) then register into it.
    _idx = _index_db_value(args)
    if _idx:
        if not _validate_index_db_rel(_idx):
            return _emit({"error": "INVALID_INDEX_DB", "field": "index_db",
                          "reason": "must be a single-line path (no newline/NUL/---)"},
                         exit_code=6)
        # TASK 025 / R-1: validate path-safety (absolute→WIKI_ALLOW_ABSOLUTE_INDEX_DB
        # gate, symlink, escape, NUL) BEFORE _ensure_index_db writes, so a rejected
        # index_db never leaves a half-applied Class-A mutation. `_idx` is already
        # edge-whitespace-free (the _validate_index_db_rel check above).
        try:
            validate_index_db_value(_idx, vault_root)
        except ConfigValidationError:
            return _emit({"error": "INVALID_INDEX_DB", "field": "index_db",
                          "reason": "index_db is unsafe or malformed (escapes the vault, "
                                    "is a symlink, or is an absolute path outside the "
                                    "framework's app-data dir without "
                                    "WIKI_ALLOW_ABSOLUTE_INDEX_DB)",
                          "hint": "An absolute index_db under the OS app-data dir "
                                  "(…/Application Support, …/.local/share, %APPDATA%) is "
                                  "trusted automatically; any other absolute path requires "
                                  "WIKI_ALLOW_ABSOLUTE_INDEX_DB=1."},
                         exit_code=6)
        if _ensure_index_db(schema_path, _idx) == "conflict":
            return _emit({"error": "INDEX_DB_ALREADY_DECLARED", "field": "index_db",
                          "reason": "WIKI_SCHEMA.md already declares a different index_db"},
                         exit_code=2)
    config = build_repo_config(
        vault_id, vault_root=vault_root,
        db_path_flag=str(args.db_path) if args.db_path else None)
    repo = make_repo(config)
    db_path = getattr(repo, "db_path", None)
    try:
        existing = repo.get_vault(vault_id)
        if existing is None:
            repo.register_vault(Vault(
                vault_id=vault_id,
                name=str(fm.get("description") or vault_id),
                root_path=vault_root,
                schema_version=str(fm.get("schema_version", "2.0")),
                registered_at=datetime.now(),
                config_json={"is_two_tier": is_two_tier,
                             "language": fm.get("language"),
                             "layout": fm.get("layout")},
            ))
            action = "registered"
        elif existing.root_path == vault_root:
            action = "already-registered"
        else:
            return _emit({
                "error": "VAULT_ID_COLLISION",
                "vault_id": vault_id,
                "existing_root_path": str(existing.root_path),
                "new_root_path": str(vault_root),
                "hint": "Pick a different vault_id, or run --reconcile if "
                        "this is a folder rename.",
            }, exit_code=6)
    finally:
        repo.close()
    # Make the registered vault agent-workable: write the selected vendor's agent
    # file(s) (CLAUDE.md by default; --vendor for GEMINI.md/all) if absent
    # (non-destructive — never clobber an operator's own file without --force).
    # Without one, an agent launched at the vault root has no wiki operating
    # instructions (DF-018-INIT-1). --vendor was validated fail-fast above.
    agent_files = _write_agent_files(
        vault_root,
        {
            "vault_id": vault_id,
            "language": str(fm.get("language") or "en"),
            "layout": str(fm.get("layout") or "per-project"),
            "description": _sanitize_desc(fm.get("description"), vault_id),
        },
        vendors, selection, vendor_settings,
        force=bool(args.force),
    )
    page_type_templates = _write_page_type_templates(
        vault_root, str(fm.get("layout") or "per-project"), force=bool(args.force))
    return _emit({
        "action": action,
        "vault_id": vault_id,
        "vault_root": str(vault_root),
        "is_two_tier": is_two_tier,
        "db_path": str(db_path),
        "agent_files": agent_files,
        "page_type_templates": page_type_templates,
    })


def reconcile(args: argparse.Namespace) -> int:
    if not args.vault:
        return _emit({"error": "MISSING_VAULT_ARG"}, exit_code=1)
    vault_root = Path(args.vault).resolve(strict=True)
    schema_path = vault_root / SCHEMA_FILE
    if not schema_path.is_file():
        return _emit({"error": "MISSING_WIKI_SCHEMA"}, exit_code=6)
    fm = _split_frontmatter(schema_path.read_text(encoding="utf-8"))
    new_vault_id = fm.get("vault_id")
    if not new_vault_id or not _validate_vault_id(new_vault_id):
        return _emit({"error": "INVALID_VAULT_ID", "received": new_vault_id},
                     exit_code=6)
    config = build_repo_config(  # TASK 022: honour a declared index_db (no silent global)
        new_vault_id, vault_root=vault_root,
        db_path_flag=str(args.db_path) if args.db_path else None)
    repo = make_repo(config)
    try:
        existing = repo.get_vault_by_root_path(vault_root)
        if existing is None:
            return _emit({
                "error": "VAULT_NOT_REGISTERED",
                "vault_root": str(vault_root),
                "hint": "Run --register-existing first",
            }, exit_code=6)
        if existing.vault_id == new_vault_id:
            return _emit({"action": "no-change", "vault_id": new_vault_id})
        if not args.confirm:
            return _emit({
                "warning": "VAULT_RENAMED",
                "old_vault_id": existing.vault_id,
                "new_vault_id": new_vault_id,
                "hint": "Re-run with --confirm to apply CASCADE rename",
            }, exit_code=7)
        old_vault_id = existing.vault_id
        repo.rename_vault(old_vault_id, new_vault_id)
        repo.append_log_event(LogEvent(
            vault_id=new_vault_id,
            event_ts=datetime.now(),
            event_type="reclassify",
            subject=f"vault rename {old_vault_id} → {new_vault_id}",
            pages_created_json=[],
            pages_updated_json=[],
            details_json={"old_vault_id": old_vault_id,
                          "new_vault_id": new_vault_id},
        ))
        return _emit({
            "action": "renamed",
            "old_vault_id": old_vault_id,
            "new_vault_id": new_vault_id,
        })
    finally:
        repo.close()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki-init",
                                description="Bootstrap or register a vault.")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--scaffold-new", action="store_true",
                       help="Create a fresh vault layout (default).")
    group.add_argument("--register-existing", action="store_true",
                       help="Register an existing vault in the DB.")
    group.add_argument("--reconcile", action="store_true",
                       help="Reconcile a renamed vault (ADR-002 §D8).")
    p.add_argument("--vault", help="Absolute path to the vault root.")
    p.add_argument("--vault-id", help="Override vault_id (scaffold-new only).")
    p.add_argument("--db-path", help="Override default DB path (testing).")
    idb = p.add_mutually_exclusive_group()
    idb.add_argument("--local", action="store_true",
                     help="TASK 022: vault-local DB at .wiki/index.db (writes index_db "
                          "into WIKI_SCHEMA.md; registers into the local DB, not global).")
    idb.add_argument("--index-db", default=None,
                     help="TASK 022: explicit vault-relative (or absolute) index DB path "
                          "to declare in WIKI_SCHEMA.md.")
    p.add_argument("--language", default=None)
    p.add_argument("--layout", default=None, choices=layout_choices())
    p.add_argument("--description", default=None)
    p.add_argument(
        "--vendor", default=None,
        help="Which agent-instruction file(s) to write (scaffold/register). "
             "Default: CLAUDE.md only. One (`gemini`), a comma-list "
             "(`claude,gemini`), or `all`. Vendors are configured in "
             "templates/agent-files.yaml.")
    p.add_argument("--force", action="store_true")
    p.add_argument("--confirm", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.register_existing:
        return register_existing(args)
    if args.reconcile:
        return reconcile(args)
    return scaffold_new(args)


if __name__ == "__main__":
    sys.exit(main())
