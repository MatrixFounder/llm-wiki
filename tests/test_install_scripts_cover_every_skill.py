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
