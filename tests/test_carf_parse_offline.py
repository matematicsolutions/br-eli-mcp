"""Offline unit test for CARF parsing - no network required.

Uses a real sample document saved from a live query against
acordaos.economia.gov.br/solr/acordaos2/select
(tests/fixtures/carf_acordao_sample.json).
"""

from __future__ import annotations

import json
from pathlib import Path

from br_eli_mcp.citations import build_caso_carf_citation, parse_caso_carf

FIXTURE = Path(__file__).parent / "fixtures" / "carf_acordao_sample.json"


def test_parse_caso_carf_from_fixture() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    docs = payload["response"]["docs"]
    assert docs, "fixture must contain at least one doc"
    raw = docs[0]

    caso = parse_caso_carf(raw)
    assert caso.numero_processo == raw["numero_processo_s"]
    assert caso.numero_decisao == raw["numero_decisao_s"]
    assert caso.ementa
    assert caso.relator == raw["nome_relator_s"]

    citation = build_caso_carf_citation(caso)
    assert citation.human_readable_citation.startswith("CARF, ")
    assert caso.numero_decisao in citation.human_readable_citation
    expected_url = (
        f"https://acordaos.economia.gov.br/acordaos2/pdfs/processados/{raw['nome_arquivo_pdf_s']}"
    )
    assert citation.lex_uri == expected_url
    assert citation.source_url == expected_url


def test_build_caso_carf_citation_no_pdf_falls_back_to_solr_endpoint() -> None:
    raw = {
        "id": "1",
        "numero_processo_s": "123",
        "numero_decisao_s": "9101-000.001",
        "nome_relator_s": "FULANO",
    }
    caso = parse_caso_carf(raw)
    citation = build_caso_carf_citation(caso)
    assert citation.lex_uri == "carf:123"
    assert citation.source_url == "https://acordaos.economia.gov.br/solr/acordaos2/select"


def test_parse_caso_carf_decisao_txt_list_joined() -> None:
    raw = {
        "id": "1",
        "numero_processo_s": "123",
        "numero_decisao_s": "9101-000.001",
        "nome_relator_s": "FULANO",
        "decisao_txt": ["linha 1", "linha 2"],
    }
    caso = parse_caso_carf(raw)
    assert caso.decisao_texto == "linha 1\nlinha 2"
