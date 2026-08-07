"""★ THE INSTALLER'S CENSUS — every skill and command SHIPS, or this goes red.

`bin/install-globally.sh` globbed `skills/wiki-*/` plus a hardcoded `obsidian-cli`. The repo's
naming convention is that a **CLI skill** is `wiki-<cli>` while a **REASON contract** is not
(`concept-extraction`, `decision-extraction`) — so that prefix filter **silently excluded every
REASON contract whose name did not happen to start with `wiki-`.**

`wiki-query-synthesis` survived by luck of its name. The other two did not:

  * `bin/install-project-symlinks.sh` globs `skills/*/` — UNFILTERED — so they WERE linked into
    the repo's own `.claude/` / `.agent/` trees, and every developer run found them;
  * `bin/install-globally.sh` did NOT — so from a **vault**, which is the only place an operator
    actually runs these rails, `Skill({skill: "concept-extraction"})` resolved to nothing.

The contract carrying the entire anti-garbage discipline never loaded on the shipped path, and
the model improvised. **Re-running the installer would never have fixed it** — the skills were
not forgotten, they were *filtered out*. That is this project's signature failure mode: a check
that enumerates the surface it *develops on* rather than the one it *ships to*.

This test is the mechanism that replaces remembering. It RUNS the real installer into a sandbox
`HOME` and asserts a 1:1 census — so a future skill named without the `wiki-` prefix cannot go
missing again, and neither can a future glob that reintroduces the filter.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
INSTALL_GLOBAL = REPO / "bin" / "install-globally.sh"
INSTALL_PROJECT = REPO / "bin" / "install-project-symlinks.sh"


def _skills() -> set[str]:
    return {d.name for d in (REPO / "skills").iterdir() if d.is_dir()}


def _commands() -> set[str]:
    # Dotfiles are not commands (`commands/.AGENTS.md` is artifact-management metadata), and a
    # bash `*.md` glob does not match them either — so the census must not either.
    return {f.name for f in (REPO / "commands").glob("*.md") if not f.name.startswith(".")}


def _run(script: Path, home: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "HOME": str(home),
        "WIKI_INSTALL_BIN": str(home / "bin"),
        # keep the installer's external-skill resolve from touching the real config tree
        "XDG_CONFIG_HOME": str(home / "config"),
    }
    return subprocess.run(
        ["bash", str(script)], cwd=REPO, env=env,
        capture_output=True, text=True, timeout=180,
    )


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_install_globally_ships_EVERY_skill_and_command(tmp_path: Path) -> None:
    """★★ THE GATE. Run the real installer into a sandbox HOME; demand a 1:1 census.

    MUT: restore the `skills/wiki-*/` glob ⇒ RED, naming `concept-extraction` and
    `decision-extraction` as the skills an operator would silently lose.
    """
    home = tmp_path / "home"
    home.mkdir()
    proc = _run(INSTALL_GLOBAL, home)
    assert proc.returncode == 0, f"installer failed:\n{proc.stdout}\n{proc.stderr}"

    linked_skills = {d.name for d in (home / ".claude" / "skills").iterdir()}
    missing = _skills() - linked_skills
    assert not missing, (
        f"★ bin/install-globally.sh did not ship: {sorted(missing)}\n"
        f"It is enumerating the skills by a NAME PREFIX instead of by the population. The last "
        f"time it did that, the two REASON contracts — the ones carrying the whole "
        f"anti-garbage discipline — were unreachable from every vault, while working perfectly "
        f"in the repo. Enumerate `skills/*/`; do not guess from a name.")

    linked_cmds = {f.name for f in (home / ".claude" / "commands").iterdir()}
    missing_cmds = _commands() - linked_cmds
    assert not missing_cmds, (
        f"★ bin/install-globally.sh did not ship the commands: {sorted(missing_cmds)}")


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_the_REASON_contracts_are_the_ones_this_test_exists_for(tmp_path: Path) -> None:
    """Named explicitly, so a future reader knows what was lost and why the census matters.

    A CLI skill teaches the agent to DRIVE the deterministic Python (`prepare`/`apply`, flags,
    exit codes). A REASON contract teaches it what to THINK, between the two. Decision-17 is
    that split — and the installer's prefix filter cut it exactly in half.
    """
    home = tmp_path / "home"
    home.mkdir()
    assert _run(INSTALL_GLOBAL, home).returncode == 0

    for reason_contract in ("concept-extraction", "decision-extraction"):
        assert reason_contract in _skills(), f"{reason_contract} vanished from skills/"
        link = home / ".claude" / "skills" / reason_contract
        assert link.is_symlink(), f"{reason_contract} was not installed globally"
        assert (link / "SKILL.md").is_file(), (
            f"{reason_contract}'s SKILL.md does not resolve through the link — the orchestrator "
            f"would silently get NO contract and improvise")


# =============================================================================
# TASK 072 / bead 072-11 — THE COMMITTED IN-REPO TREES, which nothing gated.
#
# The tests above run the installers into a SANDBOX and census the result. That
# proves the scripts are correct; it says nothing about the symlink trees actually
# COMMITTED to this repo, which are what every vendor CLI reads when working here.
# Those had drifted, silently, across five directories at once:
#
#   .claude/skills      missing wiki-config
#   .agent/skills       missing wiki-config
#   .pi/skills          missing wiki-config AND decision-extraction
#   .claude/commands    missing wiki-config.md AND wiki-reload.md
#   .agent/workflows    missing wiki-reload.md
#   .pi/skills/wiki-enrich  → a DANGLING link to a dir TASK 047 deleted
#
# The fix is `bash bin/install-project-symlinks.sh` — it was always available and
# always idempotent. Nobody ran it, because nothing said to. That is the argument
# for a test rather than a note in a README.
#
# ⚠️ THESE ASSERTIONS ARE ABOUT THE WORKING TREE, NOT ABOUT GIT — deliberately, and
# they will be RED on a fresh clone until the installer runs (README already names
# that as the fresh-clone step, and the failure message names the command). The
# mirrors are GENERATED artifacts: `.gitignore` ignores `/.claude/skills/*`,
# `/.claude/commands/*`, `/.agent/workflows/*`, `/.pi/skills/*`.
#
# RECORDED FINDING (hygiene, not fixed here): those dirs are gitignored and yet **38
# entries are still tracked** (10 + 10 + 10 + 0 + 8) — links added before the ignore
# rules landed. So a fresh clone gets a PARTIAL tree that looks plausible, which is a
# large part of why the drift stayed invisible: `ls` showed a populated directory.
# Reconciling it (untrack them, or stop ignoring) is repo hygiene with its own
# blast radius, and belongs to its own change.
# =============================================================================

_MIRRORS = {
    "skills": (".claude/skills", ".agent/skills", ".pi/skills"),
    "commands": (".claude/commands",),
    "workflows": (".agent/workflows",),
}


def _entries(rel: str) -> set[str]:
    """Non-dotfile entries of a repo dir. Dotfiles are metadata (`.AGENTS.md`), and
    the installer's own `*/` and `*.md` globs do not match them either."""
    d = REPO / rel
    return {p.name for p in d.iterdir() if not p.name.startswith(".")} if d.is_dir() else set()


@pytest.mark.parametrize("source", sorted(_MIRRORS))
def test_every_committed_vendor_mirror_carries_the_whole_source_tree(source: str) -> None:
    """★ Each vendor mirror must be a SUPERSET of its source. Superset, not equality:
    `.claude/skills` and `.agent/skills` also carry the agentic-framework skills, which
    have no counterpart under `skills/`."""
    want = _entries(source)
    assert want, f"{source}/ is empty — the census would be vacuous"
    for mirror in _MIRRORS[source]:
        missing = sorted(want - _entries(mirror))
        assert not missing, (
            f"★ {mirror}/ is missing {missing} from {source}/. Fix with "
            f"`bash bin/install-project-symlinks.sh` (idempotent; adds and repairs, "
            f"never deletes) and commit the links.")


def test_no_symlink_in_the_repo_dangles() -> None:
    """A dangling link is worse than a missing one: `ls` shows the name, so every
    eyeball census counts it as present, and only resolving it fails. `.pi/skills/
    wiki-enrich` pointed at a directory TASK 047 deleted and survived every review
    since."""
    dangling = sorted(
        str(p.relative_to(REPO))
        for p in REPO.rglob("*")
        if ".git" not in p.parts and p.is_symlink() and not p.exists()
    )
    assert dangling == [], (
        f"dangling symlinks: {dangling} — they read as PRESENT in any `ls`-based "
        f"census and fail only on resolve")


@pytest.mark.parametrize(
    ("agents_md", "source", "noun"),
    [("commands/.AGENTS.md", "commands", "commands"),
     ("workflows/.AGENTS.md", "workflows", "workflow")],
)
def test_the_agents_md_count_matches_the_directory(
    agents_md: str, source: str, noun: str
) -> None:
    """A hand-written count in a doc is a claim with a shelf life. `commands/.AGENTS.md`
    said 18 while the dir held 19; `workflows/.AGENTS.md` listed 6 of 8. Both drifted
    the moment a file was added, and neither had anything to catch it.

    The check is deliberately loose about PHRASING (it scans for any integer adjacent to
    the noun) and strict about the NUMBER — so a rewrite of the prose is free and a
    stale count is not."""
    import re

    text = (REPO / agents_md).read_text(encoding="utf-8")
    actual = len(_entries(source))
    claims = [
        int(m.group(1))
        for m in re.finditer(rf"\*?\*?(\d+)\*?\*?\s+[`\w*-]*\s*{noun}", text)
    ]
    assert claims, f"{agents_md} states no count for {noun} — nothing to keep honest"
    assert all(c == actual for c in claims), (
        f"{agents_md} claims {claims} {noun} but {source}/ holds {actual}")


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")
def test_the_two_installers_agree_on_the_population() -> None:
    """The in-repo installer globs `skills/*/`; the global one used to glob `skills/wiki-*/`.

    That disagreement is the whole bug: development saw every skill, the shipped path saw a
    subset — and nothing anywhere compared the two. Pin them together at the source level, so a
    prefix filter reintroduced in EITHER script is caught even before the sandbox run.

    ★ COMMENTS ARE STRIPPED FIRST. The string `skills/wiki-*` still appears in both files — in
    the comments that RECORD the bug, which is exactly where it belongs. A bare substring check
    would either fail on that history or bully the next author into erasing it. (This test
    caught that in itself on its first run, which is the whole argument for running a check
    before writing it into an exit criterion.)
    """
    for script in (INSTALL_GLOBAL, INSTALL_PROJECT):
        code = "\n".join(
            line for line in script.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        assert "skills/wiki-*" not in code, (
            f"{script.name} filters the skills by a `wiki-*` name prefix again. Every REASON "
            f"contract (`concept-extraction`, `decision-extraction`) is named WITHOUT that "
            f"prefix and would be dropped. Enumerate the population.")
