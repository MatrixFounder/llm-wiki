"""R-23 Phase A / DF-064-1 — the concept `definition` becomes INSPECTABLE.

★★ THE ACCEPTANCE CRITERION IS NOT "THE COLUMN IS POPULATED". IT IS THE ROUND-TRIP.

`entities.definition` is a **Class-B cache of Class-A markdown** (ADR-002 §D8): the DB must be
100% rebuildable from the files. So there are TWO writers of that column — the concepts rail
(`upsert_extracted_entity`) and the rebuilder (`reindex_full`) — and **they must agree
byte-for-byte.** If they don't, the very first `wiki-reindex --full` silently *changes* the
column, and "Class B is a rebuildable cache" is false.

The trap is real and it is one function deep: `write_concept_page` puts
`_sanitize_definition(candidate["definition"])` into the page **body** (markdown-actives get
escaped — `*args` → `\\*args`). The rebuilder reads the definition back **out of that body**.
So a writer that stored the *raw* candidate string would round-trip to a *different* value —
and every existing test would still pass, because each side is internally consistent.

That is why `test_the_definition_ROUND_TRIPS_byte_identically` exists, and why it uses a
definition containing a markdown-active character on purpose.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills._common import definition_from_concept_body
from scripts.wiki_skills.wiki_extract_concepts import main

VAULT_ID = "def-vault"

# ★ A markdown-active leading character. `sanitize_markdown_text` escapes it into the page
# body, so the bytes on disk are NOT the bytes the model sent — which is exactly the gap a
# naive writer falls into.
DEFINITION = (
    "*args в Python — упаковка позиционных аргументов в кортеж; "
    "различие с **kwargs в том, что ключи не сохраняются."
)
QUOTE = "Про упаковку позиционных аргументов мы говорили отдельно и подробно."
NAME = "Упаковка аргументов"
SLUG = "упаковка-аргументов"


def _vault(root: Path, db: Path) -> None:
    """An `obsidian-personal` vault (preserve-unicode — the operator's live layout)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "WIKI_SCHEMA.md").write_text(
        f"---\nvault_id: {VAULT_ID}\nlanguage: ru\nlayout: obsidian-personal\n---\n",
        encoding="utf-8")
    (root / "note.md").write_text(
        f"---\ntype: summary\nslug: note\n---\n# Заметка\n\n{QUOTE}\n", encoding="utf-8")

    r = SQLiteRepository(db)
    r.apply_schema()
    r.register_vault(Vault(vault_id=VAULT_ID, name=VAULT_ID, root_path=root,
                           schema_version="7.0", registered_at=datetime(2026, 7, 14)))
    r.close()
    repo = make_repo({"vault_id": VAULT_ID, "db_path": str(db), "vault_root": str(root)})
    try:
        reindex_full(repo, VAULT_ID)
    finally:
        repo.close()


def _definition_in_db(db: Path, slug: str = SLUG) -> str | None:
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT definition FROM entities WHERE vault_id = ? AND slug = ?",
            (VAULT_ID, slug),
        ).fetchone()
    finally:
        conn.close()
    return None if row is None else row[0]


def _apply(root: Path, db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["prepare", "--vault", VAULT_ID, "--vault-root", str(root),
                 "--source-page", "note.md", "--db-path", str(db)])
    prep = json.loads(capsys.readouterr().out.strip())
    assert code == 0, prep

    cands = root / "c.json"
    cands.write_text(json.dumps([{
        "slug": SLUG, "name": NAME, "definition": DEFINITION,
        # L1 `---` · L2-L3 frontmatter · L4 `---` · L5 `# Заметка` · L6 blank · L7 the quote.
        "source_quote": QUOTE, "source_span": "L7-L7", "entity_type": "concept",
    }], ensure_ascii=False), encoding="utf-8")

    code = main(["apply", "--vault", VAULT_ID, "--vault-root", str(root),
                 "--source-page", "note.md", "--source-hash", prep["source_hash"],
                 "--candidates-file", str(cands), "--db-path", str(db)])
    env = json.loads(capsys.readouterr().out.strip())
    assert code == 0, env


# --------------------------------------------------------------------------- #
# ★★ THE GATE
# --------------------------------------------------------------------------- #


def test_the_definition_ROUND_TRIPS_byte_identically(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """★★ ADR-002 §D8 — THE ACCEPTANCE CRITERION FOR R-23 PHASE A.

    `apply` writes the row. `wiki-reindex --full` **wipes and rebuilds it from the markdown
    alone.** The two values must be identical, or the DB is not a rebuildable cache of the
    files — it is a second, diverging source of truth.

    MUT: have `upsert_extracted_entity` store the RAW `candidate["definition"]` instead of the
    sanitized text ⇒ RED (the rebuild reads the escaped form back out of the body).
    """
    root, db = tmp_path / "v", tmp_path / "x.db"
    _vault(root, db)
    _apply(root, db, capsys)

    after_apply = _definition_in_db(db)
    assert after_apply, "apply wrote no definition — the column is still dead"

    # ★ and it is the SANITIZED text — the bytes the PAGE carries, not the bytes the model sent
    page = (root / "_concepts" / f"{SLUG}.md").read_text(encoding="utf-8")
    assert after_apply in page, (
        "the row holds a string the page does not contain — the writer and the page have "
        "already diverged, and the rebuild has not even run yet")
    assert after_apply != DEFINITION, (
        "this fixture's definition starts with a markdown-active `*`, so the sanitized form "
        "MUST differ from the raw candidate. If they are equal the fixture has lost its teeth "
        "and the round-trip is no longer being tested against the escaping gap.")

    repo = make_repo({"vault_id": VAULT_ID, "db_path": str(db), "vault_root": str(root)})
    try:
        reindex_full(repo, VAULT_ID)          # ← wipe + rebuild from Class A alone
    finally:
        repo.close()

    after_rebuild = _definition_in_db(db)
    assert after_rebuild == after_apply, (
        "★ ADR-002 §D8 VIOLATED: `wiki-reindex --full` CHANGED the definition.\n"
        f"  apply   : {after_apply!r}\n"
        f"  rebuild : {after_rebuild!r}\n"
        "The DB has stopped being a 100%-rebuildable cache of the markdown.")


def test_a_full_rebuild_ALONE_populates_the_definition(tmp_path: Path) -> None:
    """The column must be reachable with no rail involved at all — a vault of hand-authored
    concept pages (or one whose DB was deleted) rebuilds its definitions from the files.

    This is the half that makes the EXISTING 720-page corpus inspectable: nothing needs to be
    re-extracted, only re-indexed.
    """
    root, db = tmp_path / "v", tmp_path / "x.db"
    _vault(root, db)

    concepts = root / "_concepts"
    concepts.mkdir(parents=True, exist_ok=True)
    (concepts / "проскальзывание.md").write_text(
        "---\ntype: concept\nslug: проскальзывание\nname: Проскальзывание\n---\n"
        "# Проскальзывание\n\n"
        "Разница между ожидаемой ценой сделки и ценой её фактического исполнения.\n\n"
        "<!-- BEGIN-AUTO:mentions -->\n## Mentions across sources\n\n- [[note]]\n"
        "<!-- END-AUTO:mentions -->\n",
        encoding="utf-8")

    repo = make_repo({"vault_id": VAULT_ID, "db_path": str(db), "vault_root": str(root)})
    try:
        reindex_full(repo, VAULT_ID)
    finally:
        repo.close()

    assert _definition_in_db(db, "проскальзывание") == (
        "Разница между ожидаемой ценой сделки и ценой её фактического исполнения.")


def test_the_AUTO_block_is_NOT_swallowed_into_the_definition(tmp_path: Path) -> None:
    """The derived mentions ledger is Class B. If it leaked into the definition, every
    concept's definition would grow a list of backlinks — and would CHANGE on every render,
    so the round-trip above would flap instead of failing honestly."""
    root, db = tmp_path / "v", tmp_path / "x.db"
    _vault(root, db)
    concepts = root / "_concepts"
    concepts.mkdir(parents=True, exist_ok=True)
    (concepts / "тест.md").write_text(
        "---\ntype: concept\nslug: тест\nname: Тест\n---\n# Тест\n\n"
        "Определение, которое должно приехать в БД целиком и без хвоста.\n\n"
        "<!-- BEGIN-AUTO:mentions -->\n## Mentions across sources\n\n- [[note]]\n"
        "<!-- END-AUTO:mentions -->\n",
        encoding="utf-8")

    repo = make_repo({"vault_id": VAULT_ID, "db_path": str(db), "vault_root": str(root)})
    try:
        reindex_full(repo, VAULT_ID)
    finally:
        repo.close()

    got = _definition_in_db(db, "тест")
    assert got == "Определение, которое должно приехать в БД целиком и без хвоста."
    assert got is not None and "Mentions" not in got and "[[" not in got


# --------------------------------------------------------------------------- #
# the parser — the ONE reading of a page, used by both sides
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("body", "expected"), [
    # the shape write_concept_page emits
    ("# Имя\n\nОпределение.\n\n<!-- BEGIN-AUTO:mentions -->\nx\n<!-- END-AUTO:mentions -->\n",
     "Определение."),
    # ★ a HUMAN edited it: no H1, no AUTO block. A parser that demanded the generated shape
    # would NULL the definition on exactly the pages someone cared enough to touch.
    ("Просто определение, без заголовка.\n", "Просто определение, без заголовка."),
    # multi-paragraph, hand-expanded
    ("# Имя\n\nПервый абзац.\n\nВторой абзац.\n", "Первый абзац.\n\nВторой абзац."),
    # H1 only — genuinely no prose
    ("# Имя\n", None),
    ("", None),
    # an `#` glued to a word is NOT an H1 (no space) — it is content
    ("#DeFi — это содержание, а не заголовок.\n", "#DeFi — это содержание, а не заголовок."),
])
def test_the_parser_reads_the_page_as_a_HUMAN_would(body: str, expected: str | None) -> None:
    assert definition_from_concept_body(body) == expected
