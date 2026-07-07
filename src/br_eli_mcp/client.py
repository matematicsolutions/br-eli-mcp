"""Async httpx client for the Camara dos Deputados open-data API (dadosabertos.camara.leg.br).

Keyless, JSON, low legal risk (open data, attribution required - see SOURCES
audited from Mcp-Brasil/mcp-brasil SOURCES.md). This is the legislative
*process* (proposicoes/bills), not a consolidated-law text database - see
citations.py for why we do not fabricate a LexML URN Lex here.
"""

from __future__ import annotations

import anyio
import httpx

from .cache import HttpCache

DEFAULT_BASE_URL = "https://dadosabertos.camara.leg.br/api/v2"
DEFAULT_TIMEOUT = httpx.Timeout(40.0, connect=10.0)
USER_AGENT = "br-eli-mcp/0.6.0 (+https://github.com/matematicsolutions/br-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3


class CamaraClient:
    """Async client. Use as ``async with CamaraClient() as c: ...``."""

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

    async def __aenter__(self) -> CamaraClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    async def _get_json(self, path: str, params: dict[str, str], *, category: str) -> dict:
        url = f"{self.base_url}{path}"
        cache_key = url + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
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

    async def search_proposicoes(self, sigla_tipo: str, ano: int, itens: int = 20) -> list[dict]:
        data = await self._get_json(
            "/proposicoes",
            {
                "siglaTipo": sigla_tipo,
                "ano": str(ano),
                "itens": str(itens),
                "ordem": "DESC",
                "ordenarPor": "id",
            },
            category="search",
        )
        return data.get("dados", [])

    async def get_proposicao(self, proposicao_id: int) -> dict:
        data = await self._get_json(f"/proposicoes/{proposicao_id}", {}, category="act")
        return data.get("dados", {})
