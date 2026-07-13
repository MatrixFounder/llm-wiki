"""TASK 063-00 — ★ the RENDERED surfaces (plan-review M-6).

The operator's requirement was *"имена папок должны быть настраиваемыми + отразить
в редакторе конфигов"* — i.e. the keys must reach the OPERATOR, not merely the UI
model. Asserting `build_ui_model()` would be the TASK-061 bug shape exactly:
`FieldSpec.description` lived in the model and rendered in `serve` **alone**, and
every model-level test was green while three of four surfaces showed nothing.

Neither existing generic guard covers this block:

| existing guard | why it does NOT cover us |
|---|---|
| `test_evolution_new_schema_field_needs_no_code` | asserts on the **model**, not on any rendered surface |
| `test_description_reaches_every_surface_from_the_schema_alone` | injects a key into an **existing** parsed block; `extract_decisions` is a NEW top-level PARSED cascading block (`_PARSED_BLOCKS` + frozen dataclass + `_overlay_parsed`) — a shape it never exercises |

So this file asserts the **rendered output** of all three surfaces, and pins the
"zero interface code" claim by *counting* the pointers rather than spot-checking
that some of them are there.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.wiki_skills.wiki_config import main
from scripts.wiki_skills.wiki_config._report import build_report_model, render_html
from scripts.wiki_skills.wiki_config._uimodel import build_ui_model
from tests.test_wiki_config_serve import Client

# The population, enumerated — not "the keys are there". A schema property added
# without a dataclass field (or vice versa) changes this set, and
# `test_ui_model_pointer_count` fails rather than a surface silently gaining a
# field no parser consumes.
_POINTERS = (
    "/extract_decisions",
    "/extract_decisions/enabled",
    "/extract_decisions/dirs",
    "/extract_decisions/dirs/decision",
    "/extract_decisions/dirs/requirement",
    "/extract_decisions/dirs/risk",
)

# The DESCRIBED subset — the four LEAF pointers. The two object pointers
# (`/extract_decisions`, `/extract_decisions/dirs`) carry no `description:`, and
# that is deliberate, not an omission: NOT ONE object `$def` in the shipped schema
# carries one, and `test_resolve_description_fallback_is_inert_on_the_shipped_schema`
# goes RED the moment a block gains one — because that flip is real behavior (every
# undescribed raw-only key under the block would start rendering the block's text as
# if it were its own, and a wrong description reads as authoritative). Blocks explain
# themselves through their leaves + the schema's own comment header. The boundary is
# STATED here rather than left merely true.
_DESCRIBED = (
    "/extract_decisions/enabled",
    "/extract_decisions/dirs/decision",
    "/extract_decisions/dirs/requirement",
    "/extract_decisions/dirs/risk",
)
_UNDESCRIBED = tuple(p for p in _POINTERS if p not in _DESCRIBED)

_CONFIG = (
    "extract_decisions:\n"
    "  enabled: true\n"
    "  dirs:\n"
    "    decision: 'Решения'\n"
    "    risk: 'Риски'\n"
)


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    (tmp_path / ".wiki").mkdir(parents=True)
    (tmp_path / ".wiki" / "sync.yaml").write_text(_CONFIG, encoding="utf-8")
    return tmp_path


def test_ui_model_pointer_count(vault: Path) -> None:
    """EXACTLY 6 new pointers — the count, asserted. `x-wiki-format: path` reaches
    the model on every `dirs.*`, so the editor renders the safe-subpath check.

    MUT: drop `x-wiki-scope: cascading` from the `extract_decisions` property ⇒
    the two denominator pins in `test_wiki_config_provenance.py` (`:426`, `:612`)
    go RED — the block would silently become root-only and stop cascading.
    """
    model = build_ui_model()
    assert set(_POINTERS) <= set(model)
    assert len([p for p in model if p.startswith("/extract_decisions")]) == 6
    assert all(model[f"/extract_decisions/dirs/{c}"].fmt == "path"
               for c in ("decision", "requirement", "risk"))


def test_show_envelope_renders_the_dirs(
    vault: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """(a) `wiki-config show` — the JSON envelope. Both halves: the operator's
    VALUE (`effective`, with its provenance) and what the key MEANS
    (`descriptions`, straight from the schema).

    MUT: revert the `$defs` block ⇒ RED.
    """
    code = main(["show", ".", "--vault-root", str(vault)])
    envelope = json.loads(capsys.readouterr().out.strip())
    assert code == 0

    block = envelope["effective"]["extract_decisions"]
    assert block["enabled"] is True
    assert block["dirs"] == {
        "decision": "Решения", "requirement": "requirements", "risk": "Риски",
    }
    # the two the operator SET carry a level origin; the one they did not is a
    # `default` — the parsed-block overlay (R-061-4) is what injects it.
    assert envelope["provenance"]["/extract_decisions/dirs/decision"]["origin"] != "default"
    assert envelope["provenance"]["/extract_decisions/dirs/requirement"]["origin"] == "default"

    for pointer in _DESCRIBED:
        assert envelope["descriptions"][pointer], f"{pointer} has no rendered description"
    # ...and the boundary, MEASURED rather than asserted in prose: the two object
    # pointers are absent from `descriptions` (the envelope filters empty ones).
    assert not set(_UNDESCRIBED) & set(envelope["descriptions"])


def test_html_report_renders_the_dirs(vault: Path) -> None:
    """(b) the HTML `report` — asserted on the rendered STRING, never on the model
    that feeds it. A surface that stays green when the schema block is reverted is
    a surface that is not reading the schema, and the zero-interface-code claim is
    false for it.

    MUT: revert the `$defs` block ⇒ RED.
    """
    html = render_html(build_report_model(vault, []))
    assert "extract_decisions" in html
    assert "Решения" in html and "Риски" in html


def test_api_schema_renders_the_dirs(vault: Path) -> None:
    """(c) `serve` — the web editor's `/api/schema` payload, which is what makes
    the folder names EDITABLE in the browser. This is the surface the operator
    named.

    MUT: revert the `$defs` block ⇒ RED.
    """
    client = Client(vault)
    try:
        status, body = client.request("GET", "/api/schema")
    finally:
        client.close()
    assert status == 200
    fields = {f["pointer"]: f for f in body["fields"]}
    assert set(_POINTERS) <= set(fields)
    assert fields["/extract_decisions/dirs/decision"]["format"] == "path"
    assert "INERT" in fields["/extract_decisions/enabled"]["description"]
