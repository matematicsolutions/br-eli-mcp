"""Live smoke test against the real TST jurisprudencia backend. Network required.

v0.6.0: free-text search and exact CNJ-process-number lookup are both wired
into MCP tools (br_search_case_tst / br_get_case_tst) - the v0.5.0 blocker
(filters silently no-oping) was a wrong request shape, fixed after a browser
network trace of the real frontend. See tst_client.py module docstring.
"""

from __future__ import annotations

import pytest

from br_eli_mcp.citations import build_caso_tst_citation, parse_caso_tst
from br_eli_mcp.tst_client import TstClient


@pytest.mark.asyncio
async def test_free_text_search_narrows_the_total() -> None:
    async with TstClient() as client:
        phrase_total, items = await client.search_acordaos(
            '"adicional de insalubridade"', tipo="ACORDAO", limit=3
        )
        # 228,802 on 2026-07-07 - loose floor, not the exact snapshot
        assert phrase_total > 50_000
        assert items

        caso = parse_caso_tst(items[0])
        assert caso.numero_formatado
        assert caso.ementa

        citation = build_caso_tst_citation(caso)
        assert citation.human_readable_citation.startswith("TST, ")


@pytest.mark.asyncio
async def test_search_total_is_dedicated_not_page_count() -> None:
    async with TstClient() as client:
        total, items = await client.search_acordaos(
            '"adicional de insalubridade"', tipo="ACORDAO", limit=2
        )
        assert len(items) == 2
        assert total > len(items)


@pytest.mark.asyncio
async def test_exact_process_number_lookup_round_trips() -> None:
    async with TstClient() as client:
        # take a real case from a live search, then look it up by its own number
        _, items = await client.search_acordaos(
            '"adicional de insalubridade"', tipo="ACORDAO", limit=1
        )
        assert items
        seed = parse_caso_tst(items[0])
        assert seed.numero_formatado

        # numFormatado looks like "AIRR - 21036-38.2019.5.04.0021"
        numero = seed.numero_formatado.split(" - ", 1)[-1].strip()
        raw = await client.get_acordao(numero, tipo="ACORDAO")
        assert raw, f"exact lookup returned nothing for {numero!r}"
        found = parse_caso_tst(raw)
        assert found.numero_formatado
        assert numero in found.numero_formatado


@pytest.mark.asyncio
async def test_exact_lookup_miss_returns_empty() -> None:
    async with TstClient() as client:
        raw = await client.get_acordao("9999999-99.1901.5.99.9999", tipo="ACORDAO")
        assert raw == {}
