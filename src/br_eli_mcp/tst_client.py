"""Async httpx client for jurisprudencia-backend2.tst.jus.br - the real
backend behind the TST (Tribunal Superior do Trabalho) jurisprudencia search
frontend at https://jurisprudencia.tst.jus.br/.

Confirmed live 2026-07-07: the frontend is a React SPA that reads its API
base URL from a runtime ``/config.json`` (``base_url`` key), then POSTs to
``{base_url}/rest/pesquisa-textual/{start}/{size}``. A direct request
against that endpoint returns real, rich records: ``numero``/``numFormatado``
(process number), ``nomRelator``, ``orgaoJudicante``, ``dtaJulgamento``,
``dtaPublicacao``, ``ementa``/``ementaHtml``, ``txtInteiroTeor`` (full
ruling text), ``tipo``.

**Scope, honestly stated - important limitation**: this session confirmed
the endpoint and pagination are real and stable (repeated calls return
disjoint pages of real records, in a stable order), and that the ``tipos``
filter (document type, e.g. ``["ACORDAO"]``) measurably narrows the result
count (3.75M of 8.48M total for ``ACORDAO`` alone - confirmed live). BUT the
free-text filter fields reverse-engineered from the minified frontend bundle
(``ementa``, ``e``, ``ou``, ``termoExato``, ``numeracaoUnica`` as a
``{numero, digito, ano, orgao, tribunal, vara}`` object) did **not** change
the result count in repeated live tests - every value tried, including the
exact numeracaoUnica of a real record just returned by the endpoint itself,
still yielded the full 8,482,640-document count. Either the correct request
shape differs from what the frontend bundle appears to construct (further
fields may be injected by request middleware not visible in this static
analysis), or the public endpoint silently no-ops on filters it does not
expect from a bare HTTP client (e.g. a required session/CSRF header this
client does not send).

Per this fleet's no-guessing rule, this client does **not** claim
process-number search works. It exposes only what is confirmed:

- ``search_acordaos``: a paginated, ``tipos``-filtered browse (real doc-type
  filtering, real pagination) - use for a general "recent rulings" or
  "acordaos by type" browse, NOT a specific-case lookup.
- ``get_acordao_by_id``: fetch one record by its own opaque ``id`` (as
  returned by ``search_acordaos``) - this re-uses the same paginated
  endpoint and scans for a matching id locally (there is no dedicated
  get-by-id endpoint on this backend), so it is only useful for a record you
  already have the id for (e.g. round-tripping a search result), not for
  looking up an arbitrary known process number.

Do not extend this client to claim process-number search without a fresh,
independently confirmed request contract.
"""

from __future__ import annotations

import httpx

from .cache import HttpCache

DEFAULT_BASE_URL = "https://jurisprudencia-backend2.tst.jus.br"
DEFAULT_TIMEOUT = httpx.Timeout(40.0, connect=10.0)
USER_AGENT = "br-eli-mcp/0.5.0 (+https://github.com/matematicsolutions/br-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3

# Confirmed live 2026-07-07 via GET https://jurisprudencia.tst.jus.br/config.json
DOC_TYPES = frozenset({"ACORDAO", "DECISAO_MONOCRATICA"})


class TstClient:
    """Async client for the TST jurisprudencia search backend.

    Use as ``async with TstClient() as c: ...``.
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
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        )

    async def __aenter__(self) -> TstClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    async def _post_page(self, start: int, size: int, body: dict, *, category: str) -> dict:
        url = f"{self.base_url}/rest/pesquisa-textual/{start}/{size}"
        cache_key = "tst:" + url + ":" + repr(sorted(body.items()))
        cached = self._cache.get(cache_key)
        if cached is not None and isinstance(cached, dict):
            return cached
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = await self._http.post(url, json=body)
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
        assert last_exc is not None
        raise last_exc

    async def search_acordaos(
        self, tipo: str = "ACORDAO", page: int = 1, limit: int = 20
    ) -> list[dict]:
        """Paginated browse of TST rulings, filtered by document ``tipo``.

        This is NOT a free-text or process-number search - see module
        docstring for why. It is a real, confirmed-working doc-type filter
        + pagination.

        Args:
            tipo: one of ``DOC_TYPES`` (default ``"ACORDAO"``).
            page: 1-based page number.
            limit: page size.
        """
        start = (page - 1) * limit + 1
        body = {"tipos": [tipo]}
        data = await self._post_page(start, limit, body, category="search")
        registros = data.get("registros") or []
        return [r.get("registro", {}) for r in registros if isinstance(r, dict)]

    async def get_acordao_by_id(
        self, doc_id: str, tipo: str = "ACORDAO", scan_pages: int = 20
    ) -> dict:
        """Best-effort local scan for a record by its own ``id`` field.

        Scans up to ``scan_pages`` pages of the same browse endpoint used by
        ``search_acordaos`` - there is no dedicated get-by-id endpoint on
        this backend (see module docstring).
        """
        page_size = 50
        for page in range(1, scan_pages + 1):
            items = await self.search_acordaos(tipo=tipo, page=page, limit=page_size)
            for item in items:
                if item.get("id") == doc_id:
                    return item
            if len(items) < page_size:
                break
        return {}
