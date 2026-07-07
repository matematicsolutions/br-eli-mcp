"""Live smoke test against the real CARF Solr open-data index. Network required."""

from __future__ import annotations

import pytest

from br_eli_mcp.carf_client import CarfClient
from br_eli_mcp.citations import build_caso_carf_citation, parse_caso_carf


@pytest.mark.asyncio
async def test_search_and_get_acordao_by_numero_processo() -> None:
    async with CarfClient() as client:
        found = await client.search_acordaos(camara="1ª SEÇÃO", limit=1)
        assert found, "expected at least one 1a SECAO acordao to seed the lookup"
        numero_processo = found[0]["numero_processo_s"]

        raw = await client.get_acordao(numero_processo=numero_processo)
        assert raw, f"expected an acordao for numero_processo={numero_processo!r}"

        caso = parse_caso_carf(raw)
        assert caso.numero_processo == numero_processo
        assert caso.ementa

        citation = build_caso_carf_citation(caso)
        assert citation.human_readable_citation.startswith("CARF, ")
        assert citation.source_url.startswith("https://acordaos.economia.gov.br/")


@pytest.mark.asyncio
async def test_get_acordao_by_numero_decisao() -> None:
    async with CarfClient() as client:
        found = await client.search_acordaos(camara="1ª SEÇÃO", limit=1)
        assert found
        numero_decisao = found[0]["numero_decisao_s"]

        raw = await client.get_acordao(numero_decisao=numero_decisao)
        assert raw
        caso = parse_caso_carf(raw)
        assert caso.numero_decisao == numero_decisao
