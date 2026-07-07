"""Offline unit test for STJ Open Data parsing - no network required.

Uses a real sample record saved from a live STJ monthly "espelho" file
(tests/fixtures/stj_espelho_sample.json, orgao TERCEIRA SECAO, 2026-05).
"""

from __future__ import annotations

import json
from pathlib import Path

from br_eli_mcp.citations import build_caso_stj_citation, parse_caso_stj

FIXTURE = Path(__file__).parent / "fixtures" / "stj_espelho_sample.json"


def test_parse_caso_stj_from_fixture() -> None:
    records = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert records, "fixture must contain at least one record"
    raw = records[0]

    caso = parse_caso_stj(raw, "TERCEIRA SECAO")
    assert caso.numero_processo == raw["numeroProcesso"]
    assert caso.ministro_relator == raw["ministroRelator"]
    assert caso.ementa
    assert caso.decisao

    citation = build_caso_stj_citation(caso)
    assert citation.human_readable_citation.startswith("STJ, ")
    assert caso.ministro_relator in citation.human_readable_citation
    assert citation.lex_uri.startswith("stj:TERCEIRA SEÇÃO:")
    assert citation.source_url == "https://dadosabertos.web.stj.jus.br/dataset/"


def test_parse_caso_stj_missing_relator_omits_rel_segment() -> None:
    raw = {
        "id": "1",
        "numeroProcesso": "1234567",
        "siglaClasse": "REsp",
        "ementa": "x",
        "dataDecisao": "20260101",
    }
    caso = parse_caso_stj(raw, "TERCEIRA TURMA")
    citation = build_caso_stj_citation(caso)
    assert "Rel." not in citation.human_readable_citation
    assert "01/01/2026" in citation.human_readable_citation
