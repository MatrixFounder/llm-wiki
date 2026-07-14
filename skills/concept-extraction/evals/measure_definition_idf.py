"""★ THE REFUTATION, AS CODE — TASK 066, bead 066-04 (R-066-8).

R-23 Phase B proposed a **write-time guard** that would refuse a tautological or stub
definition, keyed on an IDF score. It was justified by a "clean separation": garbage **4.6–22.0**,
live corpus **min 29.3**.

**That claim was produced by four numbers typed by hand, and it was WRONG.**

This file exists because §2 of TASK 066 indicts the 9/11 baseline for being *"produced by hand …
not reproducible, not defensible"* — and the same task then closed a roadmap phase on four
hand-run numbers over four strings. **One evidentiary standard for what the author wanted to
BUILD, a weaker one for what he wanted to CUT.** So the refutation ships as code.

## What it measures

Total IDF carried by a definition **beyond its own name** — "how much does this say that the
title did not already say?" — with the IDF table computed over a **real corpus** of definitions,
not over a stop-list somebody thought of.

## What it FOUND — and why the guard is dead

The SKILL itself blesses a short definition as GOOD (`SKILL.md`, verbatim: *"`Форк — расхождение
цепочки блоков.` is a good definition. **Never pad to clear it.**"*).

    «Форк — расхождение цепочки блоков.»                    ← the SKILL's OWN good example
    «Синергия — это когда есть синергия между командами.»   ← GARBAGE

**The good one scores LOWER than the garbage.** The bands do not separate — they **interleave**.

The cause: the IDF **sum** is a proxy for **LENGTH**. Every definition in the live corpus is long
(80–320 chars), which is where the flattering "min 29.3" came from. **Length-normalising does not
rescue it either** — the normalised bands are ~0.1 apart and *inverted*.

## The honest conclusion (and the correction of an over-claim)

What is refuted is **the IDF-sum family**, on its **first false-positive control**. The earlier
wording — *"no scalar cutoff exists"* — was a **universal negative drawn from N=2 vs N=2**: the
very sin it condemned. **The general question is UNMEASURED.** Reopening it requires ≥30 per
class **including short-but-good definitions** — the class whose absence produced the artifact.

Run it:

    python3 skills/concept-extraction/evals/measure_definition_idf.py            # bundled corpus
    python3 skills/concept-extraction/evals/measure_definition_idf.py --db PATH  # a live vault
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

STEM = 5

#: The PROBES — every one labelled with the class it belongs to, so the test can assert the
#: bands INTERLEAVE rather than trusting a sentence that says they do.
#:
#: ★ The two "good/short" probes are the false-positive control the original sweep NEVER RAN.
#: `фoрк` is quoted from `SKILL.md` verbatim; it is the definition the skill TEACHES.
PROBES: list[dict[str, str]] = [
    {"name": "Тултип", "definition": "Тултип это тултип.",
     "cls": "garbage", "note": "a stub — restates its own name"},
    {"name": "Синергия",
     "definition": "Синергия — это когда есть синергия между командами.",
     "cls": "garbage", "note": "a tautology — the canonical case the guard existed for"},
    {"name": "Форк", "definition": "Форк — расхождение цепочки блоков.",
     "cls": "good", "note": "★ THE SKILL'S OWN EXAMPLE OF A GOOD DEFINITION"},
    {"name": "Слиппедж",
     "definition": "Разница между ожидаемой и фактической ценой сделки.",
     "cls": "good", "note": "short, specific, correct"},
]


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", unicodedata.normalize("NFC", text).casefold(), re.UNICODE)


def _stem(word: str) -> str:
    return word[:STEM]


def build_idf(corpus: list[str]) -> tuple[dict[str, float], int]:
    """IDF over the definition corpus. **No stop-list**: a word common across the corpus carries
    no information *about this corpus*, whatever a stop-list author happened to think of."""
    df: Counter[str] = Counter()
    for d in corpus:
        df.update({_stem(w) for w in _words(d)})
    n = max(len(corpus), 1)
    return {s: math.log(n / c) for s, c in df.items()}, n


def score(name: str, definition: str, idf: dict[str, float], n: int) -> float:
    """Total IDF carried BEYOND the concept's own name."""
    own = {_stem(w) for w in _words(name)}
    novel = {_stem(w) for w in _words(definition)} - own
    return sum(idf.get(s, math.log(n)) for s in novel)


def score_normalised(name: str, definition: str, idf: dict[str, float], n: int) -> float:
    """The obvious rescue attempt — mean IDF per novel word, to cancel the length effect.
    **It does not rescue it.** Recorded here because "we tried the fix" must be checkable."""
    own = {_stem(w) for w in _words(name)}
    novel = {_stem(w) for w in _words(definition)} - own
    if not novel:
        return 0.0
    return sum(idf.get(s, math.log(n)) for s in novel) / len(novel)


def _corpus_from_db(db: Path) -> list[str]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT definition FROM entities "
        "WHERE definition IS NOT NULL AND TRIM(definition) <> ''").fetchall()
    conn.close()
    return [str(r["definition"]) for r in rows]


def _bundled_corpus() -> list[str]:
    """The eval set's own definitions — so the refutation runs on a CLEAN CHECKOUT, with no
    live vault and no network. A refutation that only reproduces on the author's laptop is the
    unreproducibility this file exists to end."""
    evals = Path(__file__).resolve().parent
    out: list[str] = []
    for d in sorted(p for p in evals.iterdir() if p.is_dir()):
        f = d / "expected.json"
        if not f.is_file():
            continue
        for item in json.loads(f.read_text(encoding="utf-8")):
            if item.get("definition"):
                out.append(str(item["definition"]))
    return out


def measure(corpus: list[str]) -> dict[str, Any]:
    idf, n = build_idf(corpus)
    rows: list[dict[str, Any]] = [
        {**p,
         "idf_sum": round(score(p["name"], p["definition"], idf, n), 2),
         "idf_mean": round(score_normalised(p["name"], p["definition"], idf, n), 2)}
        for p in PROBES
    ]
    good = [r for r in rows if r["cls"] == "good"]
    bad = [r for r in rows if r["cls"] == "garbage"]

    def _interleave(key: str) -> bool:
        """★ THE VERDICT, COMPUTED — not asserted in prose. The bands INTERLEAVE when some
        garbage outscores some good: no threshold can separate them."""
        return any(float(b[key]) > float(g[key]) for b in bad for g in good)

    return {
        "corpus_size": n,
        "probes": rows,
        "idf_sum_bands_interleave": _interleave("idf_sum"),
        "idf_mean_bands_interleave": _interleave("idf_mean"),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=None,
                   help="a live index DB (else: the eval set's own definitions)")
    args = p.parse_args()

    corpus = _corpus_from_db(args.db) if args.db else _bundled_corpus()
    result = measure(corpus)

    print(f"corpus: {result['corpus_size']} definitions"
          f"{' (LIVE VAULT)' if args.db else ' (bundled eval set)'}\n")
    print(f"   {'idf_sum':>8}  {'idf_mean':>8}  {'class':8}  concept")
    for r in sorted(result["probes"], key=lambda r: float(r["idf_sum"])):
        print(f"   {r['idf_sum']:8.1f}  {r['idf_mean']:8.2f}  {r['cls']:8}  "
              f"{r['name']:10} — {r['note']}")
    print()
    print(f"   idf_sum  bands interleave: {result['idf_sum_bands_interleave']}")
    print(f"   idf_mean bands interleave: {result['idf_mean_bands_interleave']}")
    print()
    if result["idf_sum_bands_interleave"]:
        print("   ⇒ THE IDF-SUM THRESHOLD IS REFUTED: garbage outscores a definition the SKILL "
              "itself\n     teaches as GOOD. No cutoff separates them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
