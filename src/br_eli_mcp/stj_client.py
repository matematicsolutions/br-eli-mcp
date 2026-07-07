"""Async httpx client for dadosabertos.web.stj.jus.br (STJ Open Data Portal -
Superior Tribunal de Justica, Brazil's second-highest court after STF).

Confirmed live 2026-07-07 (see DISCOVERY.md "v0.5.0 update"). This is a CKAN
open-data portal, not a per-case REST lookup service: it publishes one
monthly JSON bulk-snapshot file ("espelho de acordao" - case mirror) per
orgao julgador (deciding chamber/section), each containing full case
metadata AND the full prose text of the acordao (ruling) and its ementa
(headnote/summary) - confirmed against a live sample (record dictionary at
``dicionario-espelhodoacordao.csv``, sample record
20260531.json/espelhos-de-acordaos-corte-especial).

**Scope, honestly stated**: coverage starts May 2022 ("espelhos data from
May 2022 onwards" per the portal's own CKAN metadata) - there is no public
API for pre-2022 STJ decisions on this portal. This module only reaches
what the portal actually publishes; it does not claim full historical
coverage.

**Access pattern**: this is CKAN's ``package_show`` API (to list a chamber's
monthly resource files) plus a plain HTTPS GET of each dated JSON resource
(bulk file, not a query-by-parameter endpoint). To keep this a lookup tool
rather than a bulk-download tool, this client downloads at most a bounded
number of the most recent monthly files (``MAX_MONTHS_SCANNED``) and filters
in-memory for the caller's query - it does not mirror the whole corpus
locally, consistent with the caching TTL used (search category).
"""

from __future__ import annotations

import anyio
import httpx

from .cache import HttpCache

DEFAULT_BASE_URL = "https://dadosabertos.web.stj.jus.br"
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
USER_AGENT = "br-eli-mcp/0.6.0 (+https://github.com/matematicsolutions/br-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3

# Orgao julgador (deciding chamber/section) -> CKAN dataset ("package") name.
# Confirmed live via package_list on dadosabertos.web.stj.jus.br 2026-07-07.
ORGAO_DATASET = {
    "CORTE ESPECIAL": "espelhos-de-acordaos-corte-especial",
    "PRIMEIRA SECAO": "espelhos-de-acordaos-primeira-secao",
    "PRIMEIRA TURMA": "espelhos-de-acordaos-primeira-turma",
    "QUARTA TURMA": "espelhos-de-acordaos-quarta-turma",
    "QUINTA TURMA": "espelhos-de-acordaos-quinta-turma",
    "SEGUNDA SECAO": "espelhos-de-acordaos-segunda-secao",
    "SEGUNDA TURMA": "espelhos-de-acordaos-segunda-turma",
    "SEXTA TURMA": "espelhos-de-acordaos-sexta-turma",
    "TERCEIRA SECAO": "espelhos-de-acordaos-terceira-secao",
    "TERCEIRA TURMA": "espelhos-de-acordaos-terceira-turma",
}

# Bound how many of the most recent monthly resource files a single search
# will download/scan - this is a lookup tool, not a bulk mirror.
MAX_MONTHS_SCANNED = 6


class StjClient:
    """Async client for the STJ Open Data (CKAN) portal.

    Use as ``async with StjClient() as c: ...``.
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
            follow_redirects=True,
        )

    async def __aenter__(self) -> StjClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    async def _get_json(self, url: str, *, category: str) -> dict | list:
        cache_key = "stj:" + url
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = await self._http.get(url)
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

    async def _list_monthly_resources(self, dataset: str) -> list[dict]:
        """Return this dataset's dated JSON resources, most recent first."""
        url = f"{self.base_url}/api/3/action/package_show?id={dataset}"
        data = await self._get_json(url, category="dict")
        resources = (data.get("result") or {}).get("resources") or []
        dated = [
            r
            for r in resources
            if r.get("format", "").upper() == "JSON" and r.get("name", "")[:8].isdigit()
        ]
        dated.sort(key=lambda r: r["name"], reverse=True)
        return dated

    async def _iter_recent_records(self, orgao: str):
        dataset = ORGAO_DATASET[orgao]
        resources = await self._list_monthly_resources(dataset)
        for res in resources[:MAX_MONTHS_SCANNED]:
            data = await self._get_json(res["url"], category="search")
            if isinstance(data, list):
                for rec in data:
                    yield rec

    async def search_casos(self, orgao: str, query: str, limit: int = 20) -> list[dict]:
        """Search recent acordaos (rulings) of one orgao julgador (chamber/section).

        Scans the most recent ``MAX_MONTHS_SCANNED`` monthly bulk files for
        that chamber and matches `query` against ``numeroProcesso`` (exact,
        if the query looks like a process/registration number) or against
        ``ministroRelator`` / ``ementa`` (case-insensitive substring).
        """
        digits = "".join(ch for ch in query if ch.isdigit())
        results: list[dict] = []
        async for rec in self._iter_recent_records(orgao):
            if digits and len(digits) >= 6:
                if digits in (rec.get("numeroProcesso") or "") or digits in (
                    rec.get("numeroRegistro") or ""
                ):
                    results.append(rec)
            else:
                haystack = f"{rec.get('ministroRelator', '')} {rec.get('ementa', '')}".lower()
                if query.lower() in haystack:
                    results.append(rec)
            if len(results) >= limit:
                break
        return results

    async def get_caso(self, orgao: str, numero_processo: str) -> dict:
        """Fetch one acordao (ruling) by its exact numeroProcesso within one
        orgao julgador's recent monthly files.
        """
        digits = "".join(ch for ch in numero_processo if ch.isdigit())
        async for rec in self._iter_recent_records(orgao):
            if digits and (
                digits in (rec.get("numeroProcesso") or "")
                or digits in (rec.get("numeroRegistro") or "")
            ):
                return rec
        return {}
