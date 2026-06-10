"""TASK 028 — unit tests for the query normalizer (fold + stem) and the
wiki-search FTS-expression lexer. Covers Bead 0 (core primitive) + Bead 1
(lexer safety matrix + never-unparseable invariant)."""

from __future__ import annotations

import sqlite3

import pytest

from scripts.wiki_index import query_normalizer as qn
from scripts.wiki_index.query_normalizer import (
    MIN_STEM_LEN,
    detect_script,
    fold_yo,
    normalize_term,
    stem_fts_query,
)


# --------------------------------------------------------------------------- #
# fold_yo (R-028-4(a) / Q-028-1) — always-on, case-preserving, NFC + NFD safe
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("src,exp", [
    ("ещё", "еще"),
    ("всё", "все"),
    ("Ёлка", "Елка"),          # case-preserving (Ё→Е, not е)
    ("ЕЩЁ", "ЕЩЕ"),
    ("hello", "hello"),         # non-ё identical
    ("сценарии", "сценарии"),   # ё-free Cyrillic identical
    ("a OR b", "a OR b"),       # whole-expr safe: ASCII operators untouched
    ('"ещё всё"', '"еще все"'),  # folds inside a quoted phrase too
])
def test_fold_yo(src: str, exp: str) -> None:
    assert fold_yo(src) == exp


def test_fold_yo_nfd_sequence() -> None:
    # NFD: е + combining diaeresis U+0308 → folded to plain е.
    nfd = "ё"
    assert fold_yo(nfd) == "е"
    assert fold_yo("Ё") == "Е"


def test_fold_yo_idempotent() -> None:
    assert fold_yo(fold_yo("ещё всё Ёж")) == fold_yo("ещё всё Ёж")


# --------------------------------------------------------------------------- #
# detect_script (Q-028-2) — Cyrillic→russian, Latin→english, else None
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("term,exp", [
    ("сценарии", "russian"),
    ("дофамин", "russian"),
    ("agents", "english"),
    ("Routing", "english"),
    ("аб12", "russian"),       # cyrillic + digits → russian
    ("ab12", "english"),       # latin + digits → english
    ("2024", None),            # digits only → literal
    ("日本語", None),            # CJK → literal
    ("aбv", None),             # mixed script → literal (safe)
    ("", None),
])
def test_detect_script(term: str, exp: str | None) -> None:
    assert detect_script(term) == exp


# --------------------------------------------------------------------------- #
# normalize_term — default (broadening on)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("term,atom,is_prefix", [
    ("сценарии", "сценар", True),
    ("сценарий", "сценар", True),      # sibling collapses to same stem
    ("Сценарии", "сценар", True),      # lowercased before stemming
    ("осведомление", "осведомлен", True),
    ("продуктовое", "продуктов", True),
    ("продажи", "продаж", True),
    ("agents", "agent", True),
    ("дофамин", "дофамин", True),
])
def test_normalize_term_stems(term: str, atom: str, is_prefix: bool) -> None:
    assert normalize_term(term, stem=True) == (atom, is_prefix)


@pytest.mark.parametrize("term", ["revolutionary", "ycwdmarkery", "marry", "happy"])
def test_normalize_term_prefix_guard_mutating_stem_literal(term: str) -> None:
    # English -y→-i mutates the term → a prefix would miss the original; emit
    # literal so the term always matches its own exact occurrences.
    atom, is_prefix = normalize_term(term, stem=True)
    assert is_prefix is False
    assert atom == term


def test_normalize_term_truncating_stem_still_prefixes() -> None:
    # The guard does NOT suppress healthy truncating stems (agents→agent⊂agents).
    assert normalize_term("agents", stem=True) == ("agent", True)
    assert normalize_term("сценарии", stem=True) == ("сценар", True)


def test_normalize_term_folds_then_stems() -> None:
    # ё folded BEFORE stemming.
    assert normalize_term("ещё", stem=True)[0] == normalize_term("еще", stem=True)[0]


# --- F-6: post-STEM min-length gate (catch-all-prefix guard) --------------- #
def test_min_gate_on_post_stem_length() -> None:
    # 'еще'/'ещё' (input len 3) stems to 'ещ' (len 2 < MIN 3) → emitted LITERAL,
    # NOT a catch-all 'ещ*'. Proves the gate is on the STEM, not the input.
    assert normalize_term("ещё", stem=True) == ("еще", False)
    assert normalize_term("еще", stem=True) == ("еще", False)


def test_min_gate_short_inputs_literal() -> None:
    assert normalize_term("а", stem=True) == ("а", False)
    assert normalize_term("и", stem=True) == ("и", False)


def test_no_produced_prefix_atom_below_min() -> None:
    # Adversarial (C-4): many short words → none becomes a short catch-all 'X*'.
    for w in ["а", "и", "в", "на", "ещё", "от", "до", "об"]:
        atom, is_prefix = normalize_term(w, stem=True)
        if is_prefix:
            assert len(atom) >= MIN_STEM_LEN


# --- acronym guard: ALL-CAPS multi-letter → literal ----------------------- #
@pytest.mark.parametrize("term,exp_atom", [
    ("ADR", "ADR"),
    ("КПЧ", "КПЧ"),
    ("SAP", "SAP"),
    ("2024", "2024"),
])
def test_normalize_term_acronyms_and_numbers_literal(term: str, exp_atom: str) -> None:
    assert normalize_term(term, stem=True) == (exp_atom, False)


# --- --exact (broadening off): fold only, never a prefix ------------------- #
def test_normalize_term_exact_fold_only() -> None:
    assert normalize_term("сценарии", stem=False) == ("сценарии", False)
    assert normalize_term("всё", stem=False) == ("все", False)   # fold still applied
    assert normalize_term("agents", stem=False) == ("agents", False)


# --------------------------------------------------------------------------- #
# stem_fts_query — the wiki-search FTS-expression lexer (Bead 1)
# --------------------------------------------------------------------------- #
def test_lexer_bare_query_stems() -> None:
    assert stem_fts_query("сценарии продаж", stem=True) == "сценар* продаж*"
    assert stem_fts_query("продуктовое осведомление", stem=True) == "продуктов* осведомлен*"
    assert stem_fts_query("agent сценарии", stem=True) == "agent* сценар*"   # mixed ru+en


def test_lexer_exact_is_fold_only() -> None:
    assert stem_fts_query("сценарии всё", stem=False) == "сценарии все"


@pytest.mark.parametrize("expr", [
    '"сценарии продаж"',                 # quoted phrase preserved
    'title:сценарии',                    # column filter preserved
    '{title body}:сценарии',             # multi-column filter preserved
    'сценари*',                          # already-prefix preserved
    '-всё',                              # NOT-sigil term preserved (fold still applies → -все)
    '^сценарии',                         # first-token sigil preserved
    '+продажи',                          # +sigil preserved
])
def test_lexer_preserves_structure_unstemmed(expr: str) -> None:
    # Bare-token stemming must NOT touch these; only fold_yo applies to ё.
    out = stem_fts_query(expr, stem=True)
    assert out == fold_yo(expr)


def test_lexer_operators_preserved() -> None:
    assert stem_fts_query("сценарии AND продажи", stem=True) == "сценар* AND продаж*"
    assert stem_fts_query("сценарии OR продажи", stem=True) == "сценар* OR продаж*"
    assert stem_fts_query("сценарии NOT реклама", stem=True) == "сценар* NOT реклам*"


def test_lexer_near_group_preserved() -> None:
    # NEAR(...) arg list carries ( , ) → each whitespace token is non-bare → preserved.
    expr = "NEAR(сценарии продажи, 3)"
    assert stem_fts_query(expr, stem=True) == expr


def test_lexer_fold_applies_to_sigil_term() -> None:
    # The always-on fold reaches even a preserved sigil term.
    assert stem_fts_query("-всё", stem=True) == "-все"


def test_lexer_idempotent_via_star_guard() -> None:
    # F-4: re-running the lexer on its own output is a no-op (every produced
    # bare-word token now ends in '*' → no longer a bare word → preserved).
    once = stem_fts_query("сценарии продуктовое осведомление", stem=True)
    twice = stem_fts_query(once, stem=True)
    assert once == twice


# --- never-unparseable invariant: rewritten output is valid FTS5 ---------- #
@pytest.fixture()
def fts_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    # Mirror pages_fts columns so `title:` / `{title tags}:` column filters are valid.
    conn.execute(
        "CREATE VIRTUAL TABLE t USING fts5(title, tldr, body_excerpt, tags, "
        "tokenize='unicode61 remove_diacritics 2')"
    )
    conn.execute(
        "INSERT INTO t(title, tldr, body_excerpt, tags) VALUES (?,?,?,?)",
        ("сценарии продаж", "осведомление",
         "продуктовое осведомление еще все", "сценарии"),
    )
    return conn


@pytest.mark.parametrize("raw", [
    "сценарии продаж",
    "продуктовое осведомление",
    '"сценарии продаж"',
    "сценарии AND продажи",
    "сценарии OR продажи",
    "сценарии NOT реклама",
    "NEAR(сценарии продажи, 3)",
    "title:сценарии",
    "сценари*",
    "agent сценарии",
    "ещё всё",
])
def test_rewritten_query_is_parseable_fts5(fts_conn: sqlite3.Connection, raw: str) -> None:
    rewritten = stem_fts_query(raw, stem=True)
    # Must not raise sqlite3.OperationalError (the DF-1 fallback is a net, not a crutch).
    fts_conn.execute("SELECT rowid FROM t WHERE t MATCH ?", (rewritten,)).fetchall()
