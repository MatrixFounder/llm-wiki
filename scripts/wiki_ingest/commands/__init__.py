"""F3 · Command modules for the wiki-ingest CLI.

Each subcommand lives in its own module here and exports exactly two
public symbols: `register(subparser)` and `execute(args) -> int`.
`wiki_ops.py` imports each command and wires it via `register()` at
startup; dispatch happens by argparse setting `args.func = execute`.

**Hard rule (enforced by `../../tests/test_architecture.py`)**: no
command module imports from another command module. Cross-command
helpers must live in F1 (`_safety`), F2 (`_markdown` / `_frontmatter`),
or F3-helper (`_vault` / `_classify`).
"""
