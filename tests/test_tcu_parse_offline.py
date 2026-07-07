"""Offline unit tests for TCU parsing - no network required.

Uses real responses saved live 2026-07-07 from
pesquisa.apps.tcu.gov.br/rest/publico/base/acordao-completo:

- ``tcu_resumidos_sample.json`` - ``documentosResumidos?termo=licitação``
  (search: summaries + the dedicated ``quantidadeEncontrada`` total field);
- ``tcu_documento_sample.json`` - ``documento?termo=KEY:"ACORDAO-COMPLETO-
  2763173"`` (full document: ACORDAO/RELATORIO/VOTO ruling prose).
"""

from __future__ import annotations

import json
from pathlib import Path

from br_eli_mcp.citations import build_caso_tcu_citation, parse_caso_tcu

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_caso_tcu_from_search_fixture() -> None:
    data = json.loads((FIXTURES / "tcu_resumidos_sample.json").read_text(encoding="utf-8"))
    assert data["quantidadeEncontrada"] > 0
    docs = data["documentos"]
    assert docs

    caso = parse_caso_tcu(docs[0])
    assert caso.key.startswith("ACORDAO-COMPLETO-")
    assert caso.numero
    assert caso.ano
    assert caso.colegiado
    assert caso.sumario
    # search results carry no ruling text - only the full-document endpoint does
    assert caso.acordao_texto is None
    assert caso.relatorio is None


def test_parse_caso_tcu_from_documento_fixture_carries_ruling_text() -> None:
    data = json.loads((FIXTURES / "tcu_documento_sample.json").read_text(encoding="utf-8"))
    assert data["quantidadeEncontrada"] == 1
    raw = data["documentos"][0]

    caso = parse_caso_tcu(raw)
    assert caso.key == "ACORDAO-COMPLETO-2763173"
    assert caso.numero == "1771"
    assert caso.ano == "2026"
    assert caso.colegiado == "Plenário"
    assert caso.relator == "WEDER DE OLIVEIRA"
    # real ruling prose, HTML mechanically flattened to text
    assert caso.acordao_texto and len(caso.acordao_texto) > 500
    assert caso.relatorio and len(caso.relatorio) > 5000
    assert caso.voto and len(caso.voto) > 5000
    assert "<p>" not in caso.acordao_texto
    assert "VISTOS" in caso.acordao_texto


def test_build_caso_tcu_citation() -> None:
    data = json.loads((FIXTURES / "tcu_documento_sample.json").read_text(encoding="utf-8"))
    caso = parse_caso_tcu(data["documentos"][0])
    citation = build_caso_tcu_citation(caso)
    assert citation.human_readable_citation == (
        "TCU, Acórdão 1771/2026 - Plenário, Rel. WEDER DE OLIVEIRA"
    )
    assert citation.lex_uri == "tcu:ACORDAO-COMPLETO-2763173"
    # source_url is the record's own PDF URL (upstream data, not constructed)
    assert citation.source_url == caso.url_arquivo_pdf
    assert citation.source_url.startswith("https://contas.tcu.gov.br/")


def test_build_caso_tcu_citation_without_pdf_falls_back_to_portal() -> None:
    caso = parse_caso_tcu({"KEY": "X", "NUMACORDAO": "1", "ANOACORDAO": "2020"})
    citation = build_caso_tcu_citation(caso)
    assert citation.source_url == "https://pesquisa.apps.tcu.gov.br/pesquisa/jurisprudencia"
