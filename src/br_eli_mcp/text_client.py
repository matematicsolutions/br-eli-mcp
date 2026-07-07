"""Async httpx client for normas.leg.br/api/public - the structured full-text
JSON-LD API for Brazilian Normas Juridicas.

Confirmed live 2026-07-06 (see DISCOVERY.md "v0.3.0 update"): this is a
separate host/API from legis.senado.leg.br (identification/provenance) -
normas.leg.br carries the actual schema.org Legislation tree, one node per
Parte/Livro/Titulo/Capitulo/Secao/Artigo/paragrafo, each with its own URN Lex
suffix and (for leaf nodes) inline article text. See norma_text.py for how
the tree is walked into an index and per-article text.
"""

from __future__ import annotations

import anyio
import httpx

from .cache import HttpCache

DEFAULT_BASE_URL = "https://normas.leg.br/api/public"
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
USER_AGENT = "br-eli-mcp/0.6.0 (+https://github.com/matematicsolutions/br-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3


class TextClient:
    """Async client for /normas (full JSON-LD Legislation tree by URN).

    Use as ``async with TextClient() as c: ...``.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        cache: HttpCache | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._cache = cache or HttpCache()
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    async def __aenter__(self) -> TextClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    async def get_legislation_tree(self, urn: str) -> dict:
        """Fetch the full JSON-LD Legislation tree for one URN Lex.

        The response can be several MB for a large code (e.g. Codigo Civil) -
        callers should use ``norma_text.build_index``/``extract_text`` to get
        only the part they need, not hand the whole tree to an LLM.
        """
        cache_key = "text:" + self.base_url + "/normas?urn=" + urn
        cached = self._cache.get(cache_key)
        if cached is not None and isinstance(cached, dict):
            return cached

        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = await self._http.get(
                    f"{self.base_url}/normas",
                    params={"urn": urn, "tipo_documento": "maior-detalhe"},
                )
                resp.raise_for_status()
                data = resp.json()
                self._cache.set(cache_key, data, ttl=HttpCache.ttl_for("act"))
                return data
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in _RETRY_STATUS or attempt == _MAX_ATTEMPTS - 1:
                    raise
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt == _MAX_ATTEMPTS - 1:
                    raise
            await anyio.sleep(0.5 * (2**attempt))
        assert last_exc is not None
        raise last_exc
