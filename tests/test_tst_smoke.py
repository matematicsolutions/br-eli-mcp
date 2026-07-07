"""Live smoke test against the real TST jurisprudencia backend. Network required.

No MCP tool wraps this client this release (see DISCOVERY.md "v0.5.0
update") - this test only proves the client itself still works against the
live host, for a future session that decides to wire it in.
"""

from __future__ import annotations

import pytest

from br_eli_mcp.citations import build_caso_tst_citation, parse_caso_tst
from br_eli_mcp.tst_client import TstClient


@pytest.mark.asyncio
async def test_search_acordaos_filters_by_tipo() -> None:
    async with TstClient() as client:
        items = await client.search_acordaos(tipo="ACORDAO", page=1, limit=2)
        assert len(items) >= 1

        caso = parse_caso_tst(items[0])
        assert caso.numero_formatado
        assert caso.ementa

        citation = build_caso_tst_citation(caso)
        assert citation.human_readable_citation.startswith("TST, ")
        assert citation.source_url == "https://jurisprudencia.tst.jus.br/"


@pytest.mark.asyncio
async def test_pagination_returns_mostly_disjoint_pages() -> None:
    """Pagination is real (not a no-op returning the same page twice), but
    not perfectly deterministic across separate live requests - the index
    is presumably sorted by relevance/date with ties that can shuffle
    between calls (the same non-determinism DISCOVERY.md already documents
    for DataJud under load). This asserts "mostly disjoint", not "always
    disjoint", so it does not overstate what was actually observed live.
    """
    async with TstClient() as client:
        page1 = await client.search_acordaos(tipo="ACORDAO", page=1, limit=5)
        page2 = await client.search_acordaos(tipo="ACORDAO", page=2, limit=5)
        ids1 = {r.get("id") for r in page1}
        ids2 = {r.get("id") for r in page2}
        assert ids1, "expected at least one record on page 1"
        assert ids2, "expected at least one record on page 2"
        overlap = ids1 & ids2
        assert len(overlap) < len(ids1), "pages should not be fully identical"
