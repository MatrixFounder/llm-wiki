"""Query-side normalization for the FTS search layer (TASK 028).

Two orthogonal mechanisms (ARCHITECTURE Q-028-1):

  1. **Fold — ALWAYS on** (not gated by ``--exact``): ``ё→е`` / ``Ё→Е`` on every
     query (and, separately, on the body corpus in ``normalization.py``). The
     FTS tokenizer is ``unicode61 remove_diacritics 2`` which does NOT fold the
     precomposed ``ё`` (U+0451). Folding both sides makes ``ещё``/``еще`` one
     token. ``fold_yo`` is safe on a whole FTS5 MATCH expression because ``ё``/``Ё``
     are non-ASCII and never part of FTS syntax (operators/quotes/sigils are ASCII).

  2. **Stem — default on, ``--exact`` disables**: per-term snowball stem + prefix
     ``*`` so one typed inflection matches its siblings (``сценарии``→``сценар*``
     matches ``сценарий``/``сценариев``/…). Script-detected per term: Cyrillic→
     ``russian``, Latin→``english``, anything else→literal (never mangled).

Two call sites wire this differently (Q-028-3, F-2):
  - ``wiki-search`` — ``stem_fts_query`` walks the raw MATCH expr and stems only
    bare content tokens, producing bare ``stem*`` terms.
  - ``wiki-query`` — calls ``normalize_term`` per already-tokenised word and
    quotes the result itself (``"stem"*``).

Import direction is one-way: ``normalization`` imports ``fold_yo`` from here;
this module must NOT import ``normalization`` (no cycle).
"""

from __future__ import annotations

import re

from scripts.wiki_index import _snowball

# Post-stem minimum length (Q-028-2 / F-6). A term whose STEM is shorter than
# this is emitted LITERAL (no ``*``) — a long word can collapse to a 2-char stem
# (e.g. ``еще``→``ещ``), and a short prefix like ``ещ*``/``аг*`` would be a
# catch-all that wrecks BM25 ranking and scans most of the corpus. Gate on the
# STEM length, not the input length.
MIN_STEM_LEN = 3

# Cyrillic blocks: base (U+0400–04FF) + supplement (U+0500–052F).
_CYRILLIC_RE = re.compile(r"[Ѐ-ӿԀ-ԯ]")
# Latin letters: ASCII a–z plus Latin-1/Extended-A letters (À–ɏ).
_LATIN_RE = re.compile(r"[A-Za-zÀ-ɏ]")
# A "bare word" the wiki-search lexer may stem: unicode letters/digits only
# (no underscore, no FTS sigils/operators/quotes/punctuation).
_BARE_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
# FTS5 boolean / proximity operator keywords (case-sensitive UPPERCASE in FTS5).
_FTS_OPERATORS = frozenset({"AND", "OR", "NOT", "NEAR"})


def fold_yo(text: str) -> str:
    """Fold Russian ``ё→е`` / ``Ё→Е`` (case-preserving). Handles both the
    precomposed forms (U+0451 / U+0401) and the NFD sequence (е/Е + combining
    diaeresis U+0308). Idempotent. Safe on a whole FTS5 expression."""
    return (
        text.replace("ё", "е")          # ё
        .replace("Ё", "Е")              # Ё
        .replace("ё", "е")            # NFD ё
        .replace("Ё", "Е")            # NFD Ё
    )


def detect_script(term: str) -> str | None:
    """Map a term to its snowball language by dominant script. Returns
    ``'russian'`` for Cyrillic-only, ``'english'`` for Latin-only, and ``None``
    for mixed-script / digits / other scripts (CJK, Arabic, …) → leave literal."""
    has_cyr = bool(_CYRILLIC_RE.search(term))
    has_lat = bool(_LATIN_RE.search(term))
    if has_cyr and not has_lat:
        return "russian"
    if has_lat and not has_cyr:
        return "english"
    return None


def normalize_term(term: str, *, stem: bool) -> tuple[str, bool]:
    """Normalize a single bare term. Returns ``(atom, is_prefix)`` — when
    ``is_prefix`` the caller appends ``*`` (a prefix search).

    Always folds ``ё``. When ``stem`` and the term is a stemmable single-script
    word, returns its (lowercased) stem with ``is_prefix=True``; otherwise
    returns the folded term literal (``is_prefix=False``). An ALL-UPPERCASE
    multi-letter token is treated as an acronym and left literal (don't broaden
    ``ADR``→``adr*`` / ``КПЧ``→``кпч*``). A stem shorter than ``MIN_STEM_LEN`` is
    left literal (catch-all-prefix guard, F-6)."""
    folded = fold_yo(term)
    if not stem:
        return folded, False
    # Acronym guard: ALL-CAPS multi-letter token → exact (no broadening).
    cased = [c for c in folded if c.isalpha()]
    if len(cased) >= 2 and folded.isupper():
        return folded, False
    lang = detect_script(folded)
    if lang is None:
        return folded, False
    st = _snowball.stem(folded.lower(), lang)
    if len(st) < MIN_STEM_LEN:
        return folded, False
    if not folded.lower().startswith(st):
        # The stem MUTATED the term rather than truncating it (e.g. the English
        # -y→-i rule: revolutionary→revolutionari), so a prefix `st*` would NOT
        # match the original term — a recall regression. Emit literal to
        # guarantee a term always matches its own exact occurrences (no
        # broadening for this word). Russian stems truncate, so this almost never
        # fires for ru; it mainly protects English -y/-ies words + synthetic tokens.
        return folded, False
    return st, True


def _is_bare_word(token: str) -> bool:
    """True if ``token`` is a plain content word the lexer may stem — i.e. it is
    entirely unicode letters/digits AND not an UPPERCASE FTS operator keyword.
    Any token carrying a quote, sigil (``* ^ - +``), ``:`` column filter, paren,
    comma, brace, or underscore fails this → passed through verbatim."""
    if token in _FTS_OPERATORS:
        return False
    return _BARE_WORD_RE.fullmatch(token) is not None


def stem_fts_query(query: str, *, stem: bool) -> str:
    """``wiki-search`` rewrite of a raw FTS5 MATCH expression.

    Always folds ``ё`` across the WHOLE expression (safe — ё/Ё are non-ASCII).
    When ``stem``, additionally stems each bare content token to ``stem*``,
    passing through verbatim: quoted phrases, paren groups, ``NEAR(...)`` arg
    lists, column filters (``col:`` / ``{a b}:``), already-``*`` terms, ``^``/``-``/
    ``+``-sigil terms, and the UPPERCASE operator keywords (a whitespace token
    carrying any of those chars is not a bare word, so it is preserved).

    Whitespace is normalised to single spaces (FTS is whitespace-insensitive);
    a quoted phrase ``"a b"`` survives because each half carries a ``"`` and is
    preserved verbatim then rejoined. The rewrite never turns a valid input into
    an un-parseable expression (it only replaces a bare word with ``stem*``,
    valid anywhere a bare word was)."""
    folded = fold_yo(query)
    if not stem:
        return folded
    out: list[str] = []
    for token in folded.split():
        if _is_bare_word(token):
            atom, is_prefix = normalize_term(token, stem=True)
            out.append(atom + "*" if is_prefix else atom)
        else:
            out.append(token)
    return " ".join(out)
