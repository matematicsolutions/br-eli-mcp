"""Live smoke test against the real STJ Open Data (CKAN) portal. Network required."""

from __future__ import annotations

import pytest

from br_eli_mcp.citations import build_caso_stj_citation, parse_caso_stj
from br_eli_mcp.stj_client import StjClient


@pytest.mark.asyncio
async def test_search_case_stj_corte_especial() -> None:
    async with StjClient() as client:
        raw_items = await client.search_casos("CORTE ESPECIAL", "Agravo", limit=2)
        assert len(raw_items) >= 1

        caso = parse_caso_stj(raw_items[0], "CORTE ESPECIAL")
        assert caso.numero_processo
        assert caso.ementa

        citation = build_caso_stj_citation(caso)
        assert citation.human_readable_citation.startswith("STJ, ")
        assert citation.source_url == "https://dadosabertos.web.stj.jus.br/dataset/"


@pytest.mark.asyncio
async def test_get_case_stj_by_numero() -> None:
    async with StjClient() as client:
        found = await client.search_casos("CORTE ESPECIAL", "Agravo", limit=1)
        assert found, "expected at least one CORTE ESPECIAL acordao to seed the lookup"
        numero = found[0]["numeroProcesso"]

        raw = await client.get_caso("CORTE ESPECIAL", numero)
        assert raw, f"expected an acordao for numeroProcesso={numero!r}"
        caso = parse_caso_stj(raw, "CORTE ESPECIAL")
        assert caso.numero_processo == numero
        assert caso.decisao
