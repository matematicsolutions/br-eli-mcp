"""Live smoke test against the real Camara dos Deputados API. Network required."""

from __future__ import annotations

import pytest

from br_eli_mcp.citations import build_citation, parse_proposicao
from br_eli_mcp.client import CamaraClient


@pytest.mark.asyncio
async def test_search_and_get_proposicao() -> None:
    async with CamaraClient() as client:
        raw_items = await client.search_proposicoes("PL", 2024, itens=3)
        assert len(raw_items) == 3

        first = parse_proposicao(raw_items[0])
        citation = build_citation(first)
        assert citation.human_readable_citation.startswith("PL ")
        assert citation.lex_uri.startswith("https://dadosabertos.camara.leg.br/api/v2/proposicoes/")
        assert citation.source_url.startswith("https://www.camara.leg.br/proposicoesWeb/")

        detail_raw = await client.get_proposicao(first.id)
        detail = parse_proposicao(detail_raw)
        assert detail.id == first.id
        assert detail.situacao is not None
