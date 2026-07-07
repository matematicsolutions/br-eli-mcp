"""Offline unit test for TST parsing - no network required.

Uses a real sample record saved from a live POST to
jurisprudencia-backend2.tst.jus.br/rest/pesquisa-textual (2026-07-07).

NOTE: no br_search_case_tst / br_get_case_tst MCP tool is wired in this
release - see server.py's INSTRUCTIONS and DISCOVERY.md "v0.5.0 update" for
why (confirmed-live backend, but no confirmed exact-lookup/free-text
contract, only a document-type-filtered browse). These parse/citation
helpers are kept tested and ready for a future session.
"""

from __future__ import annotations

import json
from pathlib import Path

from br_eli_mcp.citations import build_caso_tst_citation, parse_caso_tst

FIXTURE = Path(__file__).parent / "fixtures" / "tst_acordao_sample.json"


def test_parse_caso_tst_from_fixture() -> None:
    records = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert records, "fixture must contain at least one record"
    raw = records[0]

    caso = parse_caso_tst(raw)
    assert caso.numero_formatado == raw["numFormatado"]
    assert caso.nome_relator == raw["nomRelator"]
    assert caso.ementa
    assert caso.orgao_judicante == raw["orgaoJudicante"]["descricao"]
    assert caso.tipo == raw["tipo"]["nome"]

    citation = build_caso_tst_citation(caso)
    assert citation.human_readable_citation.startswith("TST, ")
    assert caso.nome_relator in citation.human_readable_citation
    assert citation.lex_uri == f"tst:{caso.id}"
    assert citation.source_url == "https://jurisprudencia.tst.jus.br/"


def test_parse_caso_tst_redacted_inteiro_teor_becomes_none() -> None:
    raw = {
        "id": "abc123",
        "numFormatado": "RR - 1-1.2020.5.01.0001",
        "nomRelator": "FULANO DE TAL",
        "orgaoJudicante": {"codigo": 1, "descricao": "1a Turma"},
        "tipo": {"codigoTipoJurisprudencia": "ACORDAO", "nome": "Acordao"},
        "ementa": "x",
        "txtInteiroTeor": "removido no backend",
    }
    caso = parse_caso_tst(raw)
    assert caso.inteiro_teor is None


def test_parse_caso_tst_missing_relator_omits_rel_segment() -> None:
    raw = {
        "id": "xyz",
        "numFormatado": "RR - 2-2.2021.5.02.0002",
        "ementa": "y",
    }
    caso = parse_caso_tst(raw)
    citation = build_caso_tst_citation(caso)
    assert "Rel." not in citation.human_readable_citation
