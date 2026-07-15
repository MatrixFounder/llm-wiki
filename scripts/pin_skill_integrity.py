"""TASK 067 (H-5) — the sanctioned RE-PIN path for skill-contract integrity.

The reasoning contracts loaded verbatim into the orchestrator's LLM context
(`skills/*/SKILL.md` carrying the `SECURITY-SENSITIVE` marker) are pinned by
SHA-256 in `config/skill-integrity.sha256`. `<rail> prepare` verifies the pin at
invocation time and STOPs on drift; the repo's test suite goes RED on an
un-re-pinned edit (`tests/test_h5_skill_integrity.py`).

After an **approved** edit to one of those contracts, regenerate the manifest::

    python3 scripts/pin_skill_integrity.py            # dry-run: show drift, exit 1 if any
    python3 scripts/pin_skill_integrity.py --write     # rewrite the manifest

The roster is **grep-derived** from `discover_integrity_roster()` (the same source
of truth the test uses — Decision-16), so a NEW banner'd contract is pinned
automatically and a stray path can never creep in. Emitting the manifest here — a
VISIBLE `config/skill-integrity.sha256` diff — is exactly the "flag the security-
sensitive change for review" control H-5 asks for, delivered without a git hook.

★ This does NOT defend against a maintainer who edits a contract AND re-pins it in
one commit — that is a branch-protection / CODEOWNERS concern, out of scope. It
turns silent tampering into a reviewable diff and a red test; that is the claim.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Bootstrap: allow `python3 scripts/pin_skill_integrity.py` (plain script) as well as
# `python3 -m scripts.pin_skill_integrity` by putting the repo root on sys.path.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.wiki_skills import _common  # noqa: E402  (referenced via the module so a test can
#                                          redirect the manifest with ONE monkeypatch)

_HEADER = (
    "# skill-contract integrity manifest (H-5 / TASK 067) — `sha256sum` format.\n"
    "# Pins every repo-owned contract file loaded VERBATIM into the orchestrator's LLM context\n"
    "#   — a skill's SKILL.md AND its references/*.md (schemas, the H-6 fence, safety-tier tables).\n"
    "# Verify out-of-band from the repo root: `sha256sum -c config/skill-integrity.sha256`.\n"
    "# Regenerate after an APPROVED edit: `python3 scripts/pin_skill_integrity.py --write`.\n"
    "# Do NOT hand-edit a hash — the diff is meant to be reviewed, not authored.\n"
)


def _desired_manifest_text() -> str:
    """The manifest content the current roster implies: header + one `<hex>  <path>` line per
    pinned contract, in the roster's (sorted) order."""
    lines = [_HEADER]
    for rel in _common.discover_integrity_roster():
        digest = _common._sha256_file(_common._REPO_ROOT / rel)
        if digest is None:  # a roster file that cannot be read — surface, do not silently skip
            raise SystemExit(f"error: cannot read pinned contract: {rel}")
        lines.append(f"{digest}  {rel}\n")
    return "".join(lines)


def _current_pins() -> dict[str, str]:
    return _common.load_integrity_manifest() or {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="Rewrite config/skill-integrity.sha256 from the current roster.")
    args = parser.parse_args(argv)

    desired_text = _desired_manifest_text()
    # Compare on the parsed {path: hash} mapping (whitespace/header-insensitive).
    current = _current_pins()
    desired: dict[str, str] = {}
    for line in desired_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, rel = line.split(None, 1)
        desired[rel.strip()] = digest.lower()

    added = sorted(set(desired) - set(current))
    removed = sorted(set(current) - set(desired))
    changed = sorted(r for r in set(desired) & set(current) if desired[r] != current[r])
    in_sync = not (added or removed or changed)

    manifest_path = _common.SKILL_INTEGRITY_MANIFEST
    if args.write:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(desired_text, encoding="utf-8")
        verb = "unchanged" if in_sync else "updated"
        try:
            shown = manifest_path.relative_to(_common._REPO_ROOT)
        except ValueError:
            shown = manifest_path
        print(f"{verb}: {shown} ({len(desired)} contracts pinned)")
        for r in added:
            print(f"  + pinned   {r}")
        for r in changed:
            print(f"  ~ re-pinned {r}")
        for r in removed:
            print(f"  - unpinned {r}")
        return 0

    # Dry-run: report drift, exit non-zero if any (so CI / a pre-commit wrapper can gate).
    if in_sync:
        print(f"in sync: {len(desired)} contracts pinned; nothing to do.")
        return 0
    print("DRIFT — config/skill-integrity.sha256 is stale. Re-pin with --write after review:")
    for r in added:
        print(f"  + would pin    {r} (new banner'd contract, unpinned)")
    for r in changed:
        print(f"  ~ would re-pin {r} (contract bytes changed since last pin)")
    for r in removed:
        print(f"  - would drop   {r} (pinned path no longer in the roster)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
