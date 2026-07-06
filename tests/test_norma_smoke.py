"""Live smoke test against the real legis.senado.leg.br Normas Juridicas API. Network required."""

from __future__ import annotations

import pytest

from br_eli_mcp.citations import build_norma_citation, parse_norma
from br_eli_mcp.norma_client import NormaClient

CODIGO_CIVIL_URN = "urn:lex:br:federal:lei:2002-01-10;10406"


@pytest.mark.asyncio
async def test_get_norma_by_urn_codigo_civil() -> None:
    async with NormaClient() as client:
        raw = await client.get_norma_by_urn(CODIGO_CIVIL_URN)
        assert raw, "expected a non-empty documento for the Codigo Civil URN"

        norma = parse_norma(raw, CODIGO_CIVIL_URN)
        assert norma.numero == "10406"
        assert "Código Civil" in (norma.apelido or "") or "Codigo Civil" in (norma.apelido or "")
        assert norma.fonte_publicacao and "Diário Oficial" in norma.fonte_publicacao
        assert len(norma.amendments) > 0

        citation = build_norma_citation(norma)
        assert citation.lex_uri == CODIGO_CIVIL_URN
        assert citation.source_url.startswith("https://normas.leg.br/")
