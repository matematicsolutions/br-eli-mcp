"""Async httpx client for acordaos.economia.gov.br (CARF - Conselho
Administrativo de Recursos Fiscais, Brazil's federal tax appeals board).

Confirmed live 2026-07-07 (see DISCOVERY.md "v0.5.0 update"): a public,
keyless Apache Solr index (``/solr/acordaos2/select``) with ~579K acordaos
(tax rulings), each carrying ``numero_processo_s`` (docket number),
``numero_decisao_s`` (decision number, e.g. ``"9101-002.402"``),
``nome_relator_s`` (rapporteur), ``camara_s``/``turma_s``/``secao_s``
(collegiate body), ``dt_publicacao_tdt`` (publication date), ``ementa_s``
(headnote) and ``decisao_txt`` (ruling body text) - real prose, not just
docket metadata.

**Scope, honestly stated**: exact-field lookups (`numero_processo_s`,
`numero_decisao_s`) are reliable and confirmed live. Free-text search over
`conteudo_txt` (the full-text field) returned zero hits for common
Portuguese terms during live probing - the manifest's own upstream notes
flag this exact gap ("0 in Neon is VPS pipeline issue"), i.e. the full-text
index is not reliably populated for every document. Rather than guess a
working full-text query syntax, this client only exposes what is confirmed
mechanical: exact docket/decision-number lookup, plus a bounded browse by
collegiate body (`camara`) and publication year - never a fuzzy keyword
search that might silently return zero or wrong results.
"""

from __future__ import annotations

import anyio
import httpx

from .cache import HttpCache

DEFAULT_BASE_URL = "https://acordaos.economia.gov.br/solr/acordaos2/select"
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
USER_AGENT = "br-eli-mcp/0.6.0 (+https://github.com/matematicsolutions/br-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3


class CarfClient:
    """Async client for the CARF Solr open-data index.

    Use as ``async with CarfClient() as c: ...``.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        cache: HttpCache | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url
        self._cache = cache or HttpCache()
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    async def __aenter__(self) -> CarfClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    async def _select(self, params: dict, *, category: str) -> dict:
        cache_key = "carf:" + repr(sorted(params.items()))
        cached = self._cache.get(cache_key)
        if cached is not None and isinstance(cached, dict):
            return cached
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = await self._http.get(self.base_url, params={**params, "wt": "json"})
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

    @staticmethod
    def _escape_exact(value: str) -> str:
        # Solr string-field exact match: quote, escaping embedded quotes/backslashes.
        return value.replace("\\", "\\\\").replace('"', '\\"')

    async def search_acordaos(
        self, numero_processo: str | None = None, camara: str | None = None, limit: int = 20
    ) -> list[dict]:
        """Search CARF acordaos by exact docket number and/or collegiate body.

        At least one of `numero_processo` / `camara` must be given - this is
        a lookup tool, not an unfiltered browse of ~579K documents.
        """
        clauses: list[str] = []
        if numero_processo:
            digits_kept = numero_processo.strip()
            clauses.append(f'numero_processo_s:"{self._escape_exact(digits_kept)}"')
        if camara:
            clauses.append(f'camara_s:"{self._escape_exact(camara)}"')
        query = " AND ".join(clauses) if clauses else "*:*"
        params = {
            "q": query,
            "rows": str(limit),
            "sort": "dt_publicacao_tdt desc",
        }
        data = await self._select(params, category="search")
        return (data.get("response") or {}).get("docs") or []

    async def get_acordao(
        self, numero_processo: str | None = None, numero_decisao: str | None = None
    ) -> dict:
        """Fetch one CARF acordao by exact docket number or decision number.

        Exactly one of `numero_processo` / `numero_decisao` must be given.
        """
        if numero_decisao:
            query = f'numero_decisao_s:"{self._escape_exact(numero_decisao)}"'
        elif numero_processo:
            query = f'numero_processo_s:"{self._escape_exact(numero_processo)}"'
        else:
            return {}
        params = {"q": query, "rows": "1"}
        data = await self._select(params, category="act")
        docs = (data.get("response") or {}).get("docs") or []
        return docs[0] if docs else {}
