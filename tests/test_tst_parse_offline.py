"""Offline unit test for TST parsing - no network required.

Uses real sample records saved from live POSTs to
jurisprudencia-backend2.tst.jus.br/rest/pesquisa-textual (2026-07-07):

- ``tst_acordao_sample.json`` - a browse-page record (v0.5.0 capture);
- ``tst_pesquisa_exact_sample.json`` - the full response of an exact
  ``numeracaoUnica`` lookup (``totalRegistros == 1``), captured in the
  v0.6.0 widen round that confirmed exact-match works (see tst_client.py).
"""

from __future__ import annotations

import json
from pathlib import Path

from br_eli_mcp.citations import build_caso_tst_citation, parse_caso_tst
from br_eli_mcp.tst_client import parse_cnj_numero

FIXTURE = Path(__file__).parent / "fixtures" / "tst_acordao_sample.json"
EXACT_FIXTURE = Path(__file__).parent / "fixtures" / "tst_pesquisa_exact_sample.json"


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


def test_exact_lookup_fixture_is_a_single_specific_case() -> None:
    """The exact-``numeracaoUnica`` response captured live: the backend's own
    dedicated total is 1 and the single record is the queried case
    (AIRR 21036-38.2019.5.04.0021), with real ruling prose attached.
    """
    data = json.loads(EXACT_FIXTURE.read_text(encoding="utf-8"))
    assert data["totalRegistros"] == 1
    raw = data["registros"][0]["registro"]

    caso = parse_caso_tst(raw)
    assert caso.numero_formatado
    assert "21036-38.2019.5.04.0021" in caso.numero_formatado
    assert caso.ementa
    assert caso.inteiro_teor and len(caso.inteiro_teor) > 1000


def test_parse_cnj_numero_accepts_formatted_stripped_and_raw() -> None:
    expected = {
        "numero": "21036",
        "digito": "38",
        "ano": "2019",
        "orgao": "5",
        "tribunal": "04",
        "vara": "0021",
    }
    assert parse_cnj_numero("21036-38.2019.5.04.0021") == expected
    raw20 = parse_cnj_numero("00210363820195040021")
    assert raw20 is not None
    assert raw20["digito"] == "38"
    assert raw20["ano"] == "2019"
    assert raw20["vara"] == "0021"
    assert raw20["numero"].lstrip("0") == "21036"


def test_parse_cnj_numero_rejects_non_cnj_input() -> None:
    assert parse_cnj_numero("not a number") is None
    assert parse_cnj_numero("12345") is None
    assert parse_cnj_numero("") is None
