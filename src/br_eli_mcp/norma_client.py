"""Async httpx client for the Congresso Nacional Dados Abertos Legislativos API
(legis.senado.leg.br/dadosabertos) - the real, live, keyless resolver for
Brazilian Normas Juridicas (LexML URN Lex).

DISCOVERY.md (2026-07-06 v0.1.0) tested the wrong host - www.lexml.gov.br,
which 404s on every candidate SRU/OAI-PMH path. The actual live service sits
on the Senado Federal's own API gateway, documented via OpenAPI 3.1 at
https://legis.senado.leg.br/dadosabertos/v3/api-docs, "acesso publico, sem
necessidade de autenticacao" - no key, no PISTE-style registration. Rate
limit: 10 req/s (HTTP 429 above that), enforced upstream, not by us.
"""

from __future__ import annotations

import anyio
import httpx

from .cache import HttpCache

DEFAULT_BASE_URL = "https://legis.senado.leg.br/dadosabertos"
DEFAULT_TIMEOUT = httpx.Timeout(40.0, connect=10.0)
USER_AGENT = "br-eli-mcp/0.6.0 (+https://github.com/matematicsolutions/br-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3


class NormaClient:
    """Async client for /legislacao/urn (Norma Juridica by URN Lex).

    Use as ``async with NormaClient() as c: ...``.
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

    async def __aenter__(self) -> NormaClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    async def _get_json(self, path: str, params: dict[str, str], *, category: str) -> dict:
        url = f"{self.base_url}{path}"
        cache_key = "norma:" + url + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        cached = self._cache.get(cache_key)
        if cached is not None and isinstance(cached, dict):
            return cached
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = await self._http.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                self._cache.set(cache_key, data, ttl=HttpCache.ttl_for(category))
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

    async def get_norma_by_urn(self, urn: str) -> dict:
        """Fetch one Norma Juridica by its URN Lex.

        Example: ``urn:lex:br:federal:lei:2002-01-10;10406`` (Codigo Civil).
        """
        data = await self._get_json("/legislacao/urn", {"urn": urn}, category="act")
        detalhe = data.get("DetalheDocumento", data)
        documentos = (detalhe.get("documentos") or {}).get("documento") or []
        if isinstance(documentos, dict):
            documentos = [documentos]
        return documentos[0] if documentos else {}
