"""Live smoke test against the real TCU pesquisa backend. Network required."""

from __future__ import annotations

import pytest

from br_eli_mcp.citations import build_caso_tcu_citation, parse_caso_tcu
from br_eli_mcp.tcu_client import TcuClient


@pytest.mark.asyncio
async def test_search_has_dedicated_total_and_summaries() -> None:
    async with TcuClient() as client:
        total, docs = await client.search_acordaos("licitação", limit=3)
        # 53,320 on 2026-07-07 - assert a loose floor, not the exact snapshot
        assert total > 10_000
        assert len(docs) == 3

        # unfiltered corpus total (525,620 on 2026-07-07)
        corpus_total, _ = await client.search_acordaos("", limit=1)
        assert corpus_total > 400_000
        assert corpus_total > total


@pytest.mark.asyncio
async def test_get_acordao_exact_lookup_returns_ruling_text() -> None:
    async with TcuClient() as client:
        # numero/ano without colegiado is ambiguous across deciding bodies
        match_count, _ = await client.get_acordao("1771", "2026")
        assert match_count >= 1

        match_count, raw = await client.get_acordao("1771", "2026", "Plenário")
        assert match_count == 1
        caso = parse_caso_tcu(raw)
        assert caso.numero == "1771"
        assert caso.ano == "2026"
        assert caso.colegiado == "Plenário"
        assert caso.acordao_texto and len(caso.acordao_texto) > 200

        citation = build_caso_tcu_citation(caso)
        assert citation.human_readable_citation.startswith("TCU, Acórdão 1771/2026")
        assert citation.source_url


@pytest.mark.asyncio
async def test_get_acordao_miss_returns_zero_matches() -> None:
    async with TcuClient() as client:
        match_count, raw = await client.get_acordao("999999", "1900")
        assert match_count == 0
        assert raw == {}
