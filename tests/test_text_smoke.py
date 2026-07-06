"""Live smoke test against the real normas.leg.br full-text API. Network required."""

from __future__ import annotations

import pytest

from br_eli_mcp.norma_text import build_index, extract_text
from br_eli_mcp.text_client import TextClient

CODIGO_CIVIL_URN = "urn:lex:br:federal:lei:2002-01-10;10406"


@pytest.mark.asyncio
async def test_index_and_text_codigo_civil() -> None:
    async with TextClient() as client:
        tree = await client.get_legislation_tree(CODIGO_CIVIL_URN)
        assert tree

        refs = build_index(tree)
        assert len(refs) > 1000, "Codigo Civil has thousands of dispositivos"

        art1 = next(r for r in refs if r.suffix == "art1")
        assert art1.tipo == "artigo"
        assert "1" in (art1.name or "")

        text = extract_text(tree, "art1")
        assert text is not None
        assert "capaz de direitos e deveres" in text

        assert extract_text(tree, "art999999") is None
