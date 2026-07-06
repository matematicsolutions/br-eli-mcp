"""Live smoke test against the real DataJud CNJ public API. Network required."""

from __future__ import annotations

import pytest

from br_eli_mcp.caselaw_client import CaselawClient
from br_eli_mcp.citations import build_processo_citation, parse_processo


@pytest.mark.asyncio
async def test_search_processos_stj_by_classe() -> None:
    async with CaselawClient() as client:
        raw_items = await client.search_processos("STJ", "Recurso Especial", limit=2)
        assert len(raw_items) >= 1

        processo = parse_processo(raw_items[0], "STJ")
        assert processo.tribunal == "STJ"
        assert processo.numero_processo
        assert len(processo.movimentos) > 0

        citation = build_processo_citation(processo)
        assert citation.human_readable_citation.startswith("STJ - Processo ")
        assert citation.source_url.startswith("https://api-publica.datajud.cnj.jus.br/")


@pytest.mark.asyncio
async def test_get_processo_by_numero() -> None:
    async with CaselawClient() as client:
        found = await client.search_processos("STJ", "Agravo", limit=1)
        assert found, "expected at least one STJ docket to seed the lookup"
        numero = found[0]["numeroProcesso"]

        raw = await client.get_processo("STJ", numero)
        assert raw, f"expected a docket for numeroProcesso={numero!r}"
        processo = parse_processo(raw, "STJ")
        assert processo.numero_processo == numero


@pytest.mark.asyncio
async def test_stf_is_not_covered() -> None:
    """Confirmed live 2026-07-06: api_publica_stf does not exist (404,
    index_not_found_exception) - STF is out of DataJud's scope by design.
    """
    import httpx

    async with CaselawClient() as client:
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client._post_search("api_publica_stf", {"query": {"match_all": {}}, "size": 1}, category="search")
        assert exc_info.value.response.status_code == 404
