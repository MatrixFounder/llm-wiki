"""S5 — `wiki_import_article.apply` facade (R-4/R-5/R-7)."""
from __future__ import annotations

import json

import pytest

import scripts.wiki_skills.wiki_import_article as wia


@pytest.fixture
def vault(tmp_path):
    (tmp_path / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: testv\nlayout: obsidian-personal\nlanguage: ru\n---\n", encoding="utf-8")
    (tmp_path / "05 - Материалы" / "Криптовалюты").mkdir(parents=True)
    return tmp_path


@pytest.fixture(autouse=True)
def _stub_subprocs(monkeypatch):
    calls = {"index": [], "concepts": []}
    monkeypatch.setattr(wia, "_index_note",
                        lambda v, root, db, p: (calls["index"].append(p) or (0, {"action": "upserted"})))
    monkeypatch.setattr(wia, "_file_concepts",
                        lambda v, root, db, sp, sh, cands: (calls["concepts"].append((sp, sh, cands)) or (0, {"created": len(cands)})))
    return calls


def _note(tmp_path, **over):
    note = {
        # summary mode renders bullets/tldr (not ru_body) → AMM's quote lives in a bullet
        "title_ru": "DeFi гайд", "tldr": "кратко",
        "summary_bullets": ["AMM это маркет-мейкер."], "ru_body": "AMM это маркет-мейкер. полный текст.",
        "entities": [
            {"name": "AMM", "definition": "автоматический маркет-мейкер",
             "quote": "AMM это маркет-мейкер.", "type": "concept"},
            {"name": "DeFi", "definition": "финансы", "quote": "x", "type": "concept"},
            {"name": "DeFi гайд", "definition": "сам гайд", "quote": "y", "type": "concept"},
        ],
    }
    note.update(over)
    f = tmp_path / "note.json"
    f.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")
    return f


def _run(vault, note_file, db, extra=None, existing='["defi"]'):
    argv = ["apply", "--vault", "testv", "--vault-root", str(vault),
            "--db-path", str(db), "--folder", "05 - Материалы/Криптовалюты",
            "--mode", "summary", "--note-file", str(note_file),
            "--raw-rel", "05 - Материалы/Криптовалюты/_raw/x.md",
            "--source-url", "https://e.com/x", "--today", "2026-06-18",
            "--existing-page-slugs", existing]
    return wia.main(argv + (extra or []))


def test_apply_meeting_kind_sets_meeting_summary_type(vault, tmp_path, capsys, _stub_subprocs):
    rc = _run(vault, _note(tmp_path), vault / "index.db", extra=["--kind", "meeting"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert "type: meeting-summary" in (vault / out["note"]).read_text()


def test_apply_karpathy_files_note_to_sources(tmp_path, capsys, _stub_subprocs):
    # a karpathy vault → note lands in _sources/, type falls back to `summary`
    # (karpathy.yaml has no `article-summary` mapping)
    (tmp_path / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: kv\nlayout: karpathy\n---\n", encoding="utf-8")
    (tmp_path / "_sources").mkdir()
    nf = tmp_path / "note.json"
    nf.write_text(json.dumps({
        "title_ru": "Kp Article", "tldr": "t", "summary_bullets": ["b"],
        "ru_body": "AMM body.", "entities": [
            {"name": "AMM", "definition": "d", "quote": "AMM body.", "type": "concept"}]},
        ensure_ascii=False), encoding="utf-8")
    rc = wia.main([
        "apply", "--vault", "kv", "--vault-root", str(tmp_path), "--db-path", str(tmp_path / "i.db"),
        "--folder", "_sources", "--mode", "full", "--kind", "article", "--note-file", str(nf),
        "--raw-rel", "_sources/_raw/x.md", "--source-url", "https://e.com/x", "--today", "2026-06-18"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["note"].startswith("_sources/")          # filed under _sources/ (karpathy)
    assert "type: summary" in (tmp_path / out["note"]).read_text()  # layout-safe fallback


def test_apply_karpathy_neutral_title_no_keyerror(tmp_path, capsys, _stub_subprocs):
    # round-12 HIGH: karpathy is the only source_filename:slug layout → apply mints the FILENAME
    # from the title. A contract-conformant NEUTRAL {title} note (no legacy title_ru) must NOT
    # KeyError in that branch — it files cleanly under _sources/<slug>.md.
    (tmp_path / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: kv\nlayout: karpathy\n---\n", encoding="utf-8")
    (tmp_path / "_sources").mkdir()
    nf = tmp_path / "note.json"
    nf.write_text(json.dumps({
        "title": "Neutral Karpathy Title", "tldr": "t", "summary_bullets": ["b"],
        "body": "AMM body.", "entities": [
            {"name": "AMM", "definition": "d", "quote": "AMM body.", "type": "concept"}]},
        ensure_ascii=False), encoding="utf-8")
    rc = wia.main([
        "apply", "--vault", "kv", "--vault-root", str(tmp_path), "--db-path", str(tmp_path / "i.db"),
        "--folder", "_sources", "--mode", "full", "--kind", "article", "--note-file", str(nf),
        "--raw-rel", "_sources/_raw/x.md", "--source-url", "https://e.com/x", "--today", "2026-06-18"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and "error" not in out                 # no KeyError → INTERNAL_ERROR
    assert out["note"] == "_sources/neutral-karpathy-title.md"   # filename minted from `title`


def test_apply_writes_note_and_files_concepts(vault, tmp_path, capsys, _stub_subprocs):
    rc = _run(vault, _note(tmp_path), vault / "index.db")
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["action"] == "imported"
    assert out["note"] == "05 - Материалы/Криптовалюты/DeFi гайд.md"
    note_path = vault / out["note"]
    assert note_path.exists()
    assert "## Ключевые выводы" in note_path.read_text()
    assert len(out["note_hash"]) == 64
    # only AMM survives the collision guard
    assert out["candidates"] == 1
    reasons = {s["reason"] for s in out["skipped"]}
    assert reasons == {"collides-existing-page", "self-collision"}
    # _file_concepts got the FRESH note hash + the note's own rel path as source-page
    sp, sh, cands = _stub_subprocs["concepts"][0]
    assert sp == out["note"] and sh == out["note_hash"]
    assert [c["slug"] for c in cands] == ["amm"]


def test_apply_no_candidates_skips_concept_filing(vault, tmp_path, capsys, _stub_subprocs):
    # every entity collides → no candidates → _file_concepts not called
    nf = _note(tmp_path, entities=[{"name": "DeFi", "definition": "d", "quote": "q", "type": "concept"}])
    rc = _run(vault, nf, vault / "index.db")
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["candidates"] == 0
    assert _stub_subprocs["concepts"] == []


def test_footer_omits_unresolvable_entities(vault, tmp_path, capsys, _stub_subprocs):
    # P3-8: the `## Ключевые сущности` footer must list ONLY entities that resolve to a page.
    # _note has AMM (filed), DeFi (collides EXISTING → page exists → linked), and
    # "DeFi гайд" (self-collision → no page) → the last must NOT be a dangling [[wikilink]].
    rc = _run(vault, _note(tmp_path), vault / "index.db")
    out = json.loads(capsys.readouterr().out)
    body = (vault / out["note"]).read_text()
    # footer links target the MINTED slug (alias-displaying the name) so they resolve under
    # every layout (incl. karpathy/identity, where a verbatim [[Name]] would orphan).
    assert "[[amm|AMM]]" in body
    assert "[[defi|DeFi]]" in body       # collides-existing → the existing page resolves it
    assert "[[defi-гайд" not in body     # self-collision → dropped from the footer (no dangling)


def test_overflow_entities_reported_not_silently_dropped(vault, tmp_path, capsys, _stub_subprocs):
    # P3-8: entities past the candidate cap are reported in skipped[] (reason max-candidates),
    # never silently dropped (which would leave dangling footer links).
    ents = [{"name": f"Концепт{i}", "definition": "d",
             "quote": f"Концепт{i} это нечто важное и описанное.", "type": "concept"}
            for i in range(30)]
    body = " ".join(e["quote"] for e in ents)
    nf = _note(tmp_path, ru_body=body, entities=ents)
    rc = _run(vault, nf, vault / "index.db", existing="[]", extra=["--mode", "full"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["candidates"] == 25  # the raised cap
    assert sum(1 for s in out["skipped"] if s["reason"] == "max-candidates") == 5


def test_full_mode_strips_dangling_image_embeds(vault, tmp_path, capsys, _stub_subprocs):
    # P3-7: `![[Attachments/<hash>]]` embeds (html2md --no-download-images) must not leak
    # into the body — they never resolve in the vault and would be dangling links.
    body = ("[![[Attachments/abc123_MD5.png]]](https://cdn/x.png)\n\n"
            "Реальный абзац перевода со смыслом.\n\n"
            "# [![[Attachments/def456_MD5.jpg]]](/)\n")
    nf = _note(tmp_path, ru_body=body,
               entities=[{"name": "AMM", "definition": "d", "quote": "AMM",
                          "type": "concept"}])
    rc = _run(vault, nf, vault / "index.db", extra=["--mode", "full"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    text = (vault / out["note"]).read_text()
    assert "[[Attachments/" not in text                 # all embeds stripped
    assert "Реальный абзац перевода со смыслом." in text  # real prose kept


def test_apply_partial_on_index_failure(vault, tmp_path, capsys, monkeypatch):
    # a failed source-note index must SKIP concept-filing (refs can't attach to a missing
    # pages row) — no orphan _concepts/ pages, report partial.
    filed = []
    monkeypatch.setattr(wia, "_index_note", lambda *a: (6, {"error": "UPSERT_FAILED"}))
    monkeypatch.setattr(wia, "_file_concepts", lambda *a: (filed.append(a) or (0, {"created": 1})))
    rc = _run(vault, _note(tmp_path), vault / "index.db")
    out = json.loads(capsys.readouterr().out)
    assert rc == 6 and out["action"] == "partial"
    assert filed == []                                   # concept-filing was skipped
    assert "skipped" in out["concepts"]["note"]


def test_apply_non_string_quote_rejected_clean_envelope(vault, tmp_path, capsys, _stub_subprocs):
    # CWE-209: an entity `quote` that is a truthy non-string (e.g. a list) must yield a clean
    # BAD_NOTE_JSON envelope, NOT a raw .strip()/find() traceback (Decision-17 one-envelope).
    nf = _note(tmp_path, entities=[
        {"name": "AMM", "definition": "d", "quote": ["not", "a", "string"], "type": "concept"}])
    rc = _run(vault, nf, vault / "index.db")
    out = json.loads(capsys.readouterr().out)
    assert rc != 0 and out.get("error") == "BAD_NOTE_JSON"


def test_apply_frontmatter_injection_is_neutralized(vault, tmp_path, capsys, _stub_subprocs):
    # hostile orchestrator fields: newline in title_ru/author → must NOT inject a YAML key
    nf = _note(tmp_path, title_ru="Заголовок\ninjected_key: pwned",
               author="Автор\nadmin: true",
               entities=[{"name": "AMM", "definition": "d", "quote": "AMM это маркет-мейкер.", "type": "concept"}])
    rc = _run(vault, nf, vault / "index.db")
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    text = (vault / out["note"]).read_text()
    fm = text.split("---\n", 2)[1]  # the frontmatter block
    # the hostile content is harmlessly inside QUOTED scalars — no STANDALONE injected key line
    keys = {ln.split(":", 1)[0].strip() for ln in fm.splitlines() if ":" in ln and not ln.startswith(" ")}
    assert "injected_key" not in keys and "admin" not in keys
    # and it must parse as valid YAML with the expected top-level keys only
    import yaml
    parsed = yaml.safe_load(fm)
    assert "injected_key" not in parsed and "admin" not in parsed


def test_apply_existing_slugs_scalar_does_not_crash(vault, tmp_path, capsys, _stub_subprocs):
    # a non-array --existing-page-slugs must be treated as empty, not list('defi')
    rc = _run(vault, _note(tmp_path), vault / "index.db", existing='"defi"')
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    # with no real existing-slug guard, DeFi is no longer collides-existing (slug set empty),
    # but the note's own-slug self-collision still fires
    reasons = {s["reason"] for s in out["skipped"]}
    assert "self-collision" in reasons


def test_tags_come_from_note_content_not_folder(vault, tmp_path, capsys, _stub_subprocs):
    # tags are a CONTENT property from the REASON step — sanitized, used verbatim
    nf = _note(tmp_path, tags=["AI", "LLM", "cost optimization"])
    rc = _run(vault, nf, vault / "index.db")
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    fm = (vault / out["note"]).read_text().split("---")[1]
    assert "tags: [ai, llm, cost-optimization]" in fm


def test_tags_default_minimal_no_folder_heuristic(vault, tmp_path, capsys, _stub_subprocs):
    # no tags in the note + a "Криптовалюты" folder → NO injected defi/crypto tags
    # (the old folder→tag hardcode is gone); just the generic fallback.
    rc = _run(vault, _note(tmp_path), vault / "index.db")
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    fm = (vault / out["note"]).read_text().split("---")[1]
    assert "tags: [article]" in fm and "crypto" not in fm and "defi" not in fm


def test_apply_missing_folder_clean_envelope(vault, tmp_path, capsys, _stub_subprocs):
    # a non-existent --folder must yield a clean INVALID_FOLDER envelope, not a FileNotFoundError
    # traceback (validate_inside_vault resolve(strict=True) on a folder that isn't on disk).
    argv = ["apply", "--vault", "testv", "--vault-root", str(vault),
            "--db-path", str(vault / "index.db"), "--folder", "05 - Материалы/Несуществующая",
            "--mode", "summary", "--note-file", str(_note(tmp_path)),
            "--raw-rel", "05 - Материалы/Несуществующая/_raw/x.md",
            "--source-url", "https://e.com/x", "--today", "2026-06-18",
            "--existing-page-slugs", "[]"]
    rc = wia.main(argv)
    out = json.loads(capsys.readouterr().out)
    assert rc != 0 and out.get("error") == "INVALID_FOLDER"


@pytest.mark.parametrize("layout,folder,expected", [
    ("karpathy", "_sources", True),                    # _concepts/**/*.md glob + concept mapping
    ("obsidian-personal", "05 - Материалы/Крипто", True),
    ("cybos", "decisions", True),                       # round-10: recursive globs + concept mapping
    ("dev-project", "tasks", False),                    # single-level globs can't reach _concepts
])
def test_layout_indexes_concepts_gate(tmp_path, layout, folder, expected):
    # the concept-filing gate: only concept-graph-capable layouts (can index a _concepts page)
    # get concept extraction; dev-project (structured-doc, single-level globs) cleanly skips it.
    from scripts.wiki_index.layout_config import resolve_layout_config
    (tmp_path / "WIKI_SCHEMA.md").write_text(
        f"---\nvault_id: gatev\nlayout: {layout}\n---\n", encoding="utf-8")
    lc = resolve_layout_config(tmp_path)
    note_dir = wia._note_dir(lc, tmp_path, tmp_path / folder)
    assert wia._layout_indexes_concepts(lc, tmp_path, note_dir) is expected


def test_vault_language_schemaless_falls_back_to_en(tmp_path):
    # round-13 regression: a SCHEMALESS vault (no WIKI_SCHEMA.md — the byte-identity karpathy
    # back-compat path resolve_layout_config supports) must NOT crash resolving the note
    # language; load_root_config raises VaultRootNotFoundError there → guarded → 'en'.
    assert wia._vault_language(tmp_path) == "en"              # no WIKI_SCHEMA.md present
    (tmp_path / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: lv\nlayout: obsidian-personal\nlanguage: ru\n---\n", encoding="utf-8")
    assert wia._vault_language(tmp_path) == "ru"              # schema present → its language


def test_mint_strategy_matches_indexer_keyspace():
    # the collision-guard mint keyspace MUST equal the indexer's for every lowercase strategy
    # (else a minted slug is compared against a differently-keyed pages.slug → missed collision
    # → owner-page eviction). Only `identity` (case-preserving) falls back to preserve-unicode.
    assert wia._mint_strategy("transliterate") == "transliterate"
    assert wia._mint_strategy("preserve-unicode") == "preserve-unicode"
    assert wia._mint_strategy("ascii-only") == "ascii-only"     # the round-5 gap, now closed
    assert wia._mint_strategy("identity") == "preserve-unicode"  # case-preserving → mint-valid


def test_apply_accepts_neutral_field_names(vault, tmp_path, capsys, _stub_subprocs):
    # international contract: neutral `title`/`body` work (legacy `title_ru`/`ru_body` still do)
    nf = tmp_path / "neutral.json"
    nf.write_text(json.dumps({"title": "Neutral Title", "tldr": "t",
        "summary_bullets": ["a bullet"], "body": "full body", "entities": []},
        ensure_ascii=False), encoding="utf-8")
    rc = _run(vault, nf, vault / "index.db")
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert 'title: "Neutral Title"' in (vault / out["note"]).read_text()


def test_non_list_tags_rejected_clean_envelope(vault, tmp_path, capsys, _stub_subprocs):
    # a bare-string `tags` would iterate per-CHAR into garbage `tags: [c, r, y, p, t, o]`;
    # the type gate must reject it with a clean BAD_NOTE_JSON (consistency with the other
    # consumed fields), not silently leak corrupt frontmatter into the filed note.
    nf = _note(tmp_path, tags="crypto")
    rc = _run(vault, nf, vault / "index.db")
    out = json.loads(capsys.readouterr().out)
    assert rc != 0 and out.get("error") == "BAD_NOTE_JSON"


def test_non_dict_entity_rejected_clean_envelope(vault, tmp_path, capsys, _stub_subprocs):
    # CWE-209: a malformed entities[] (non-dict element) yields a clean BAD_NOTE_JSON
    # envelope, NOT an uncaught AttributeError stack trace.
    nf = tmp_path / "bad.json"
    nf.write_text(json.dumps({"title_ru": "T", "tldr": "t", "summary_bullets": ["b"],
                              "ru_body": "x", "entities": ["not-a-dict", 123]}), encoding="utf-8")
    rc = _run(vault, nf, vault / "index.db")
    out = json.loads(capsys.readouterr().out)
    assert rc != 0 and out.get("error") == "BAD_NOTE_JSON"
