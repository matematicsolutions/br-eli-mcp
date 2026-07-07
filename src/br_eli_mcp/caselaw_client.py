"""Async httpx client for api-publica.datajud.cnj.jus.br (DataJud CNJ) -
the real, unified Elasticsearch-backed public API for Brazilian court dockets.

Confirmed live 2026-07-06 (see DISCOVERY.md "v0.4.0 update") with a real HTTP
request against the STJ index. Authentication uses a single API key that CNJ
itself publishes openly on the DataJud Wiki
(https://datajud-wiki.cnj.jus.br/api-publica/acesso/) for public use - not a
per-developer secret, comparable to other Brazilian open-data patterns. CNJ
states the key "pode ser alterada... a qualquer momento" (may change at any
time) - see ``DATAJUD_PUBLIC_KEY`` below and its override env var.

**Scope, honestly stated**: DataJud indexes *docket metadata* - process
number, classe, orgao julgador, assuntos, and the full ``movimentos``
(procedural timeline: distribuicao, conclusao, publicacao, decisions-as-
events, etc.) - sourced from each court's own case management system via the
Modelo Nacional de Interoperabilidade. It does **not** carry the prose text of
a ruling/acordao/ementa. That is a real, separate gap - see DISCOVERY.md - and
this module does not pretend otherwise: it is a docket/movement search, not a
full-text jurisprudencia search.

**STF is not covered.** Querying ``api_publica_stf`` returns HTTP 404
(``index_not_found_exception``) - confirmed live. The STF is constitutionally
autonomous from the CNJ's regulatory reach in a way the other courts (STJ,
TST, TSE, TRFs, TJs, TRTs, TREs, military courts) are not, so it does not feed
DataJud. There is no api_publica_stf index to query, by design, not by outage.

**Redistribution note** (Resolucao CNJ 446/2022): bulk redistribution of
DataJud data is restricted, and case data can carry LGPD-sensitive party
information. This client only performs live, on-demand queries (bring-your-
own-shared-key, same key CNJ itself publishes) - it never bulk-downloads or
persists a corpus, consistent with the caching TTL used for search results
(short - "list" category, not "act").
"""

from __future__ import annotations

import os

import anyio
import httpx

from .cache import HttpCache

DEFAULT_BASE_URL = "https://api-publica.datajud.cnj.jus.br"
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
USER_AGENT = "br-eli-mcp/0.6.0 (+https://github.com/matematicsolutions/br-eli-mcp)"

# CNJ publishes this key openly on the DataJud Wiki for public use; it can be
# rotated by CNJ at any time (per their own wiki), so allow an env override
# rather than hardcoding an expectation that this never changes.
DATAJUD_PUBLIC_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3

# Tribunal alias -> DataJud index name, confirmed live via
# https://datajud-wiki.cnj.jus.br/api-publica/endpoints/ (2026-07-06).
# STF is intentionally absent - see module docstring.
TRIBUNAL_INDEX = {
    "STJ": "api_publica_stj",
    "TST": "api_publica_tst",
    "TSE": "api_publica_tse",
    "STM": "api_publica_stm",
    **{f"TRF{n}": f"api_publica_trf{n}" for n in range(1, 7)},
    **{
        f"TJ{uf}": f"api_publica_tj{uf.lower()}"
        for uf in [
            "AC",
            "AL",
            "AM",
            "AP",
            "BA",
            "CE",
            "DFT",
            "ES",
            "GO",
            "MA",
            "MG",
            "MS",
            "MT",
            "PA",
            "PB",
            "PE",
            "PI",
            "PR",
            "RJ",
            "RN",
            "RO",
            "RR",
            "RS",
            "SC",
            "SE",
            "SP",
            "TO",
        ]
    },
    **{f"TRT{n}": f"api_publica_trt{n}" for n in range(1, 25)},
    **{
        f"TRE-{uf}": f"api_publica_tre-{uf.lower()}"
        for uf in [
            "AC",
            "AL",
            "AM",
            "AP",
            "BA",
            "CE",
            "DFT",
            "ES",
            "GO",
            "MA",
            "MG",
            "MS",
            "MT",
            "PA",
            "PB",
            "PE",
            "PI",
            "PR",
            "RJ",
            "RN",
            "RO",
            "RR",
            "RS",
            "SC",
            "SE",
            "SP",
            "TO",
        ]
    },
    "TJM-MG": "api_publica_tjmmg",
    "TJM-RS": "api_publica_tjmrs",
    "TJM-SP": "api_publica_tjmsp",
}


def _api_key() -> str:
    return os.environ.get("BR_ELI_DATAJUD_KEY", DATAJUD_PUBLIC_KEY)


class CaselawClient:
    """Async client for the DataJud CNJ public API (docket search by tribunal).

    Use as ``async with CaselawClient() as c: ...``.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        cache: HttpCache | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._cache = cache or HttpCache()
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"APIKey {api_key or _api_key()}",
            },
        )

    async def __aenter__(self) -> CaselawClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    async def _post_search(self, index: str, body: dict, *, category: str) -> dict:
        url = f"{self.base_url}/{index}/_search"
        cache_key = "caselaw:" + url + ":" + repr(sorted(body.items()))
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
            await anyio.sleep(0.5 * (2**attempt))
        assert last_exc is not None
        raise last_exc

    async def search_processos(self, tribunal: str, query: str, limit: int = 20) -> list[dict]:
        """Free-text search (classe/assuntos/orgaoJulgador/numeroProcesso) within
        one tribunal's DataJud index.

        Args:
            tribunal: a key in ``TRIBUNAL_INDEX``, e.g. ``"STJ"``.
            query: free text - matched against ``numeroProcesso``, or (if it
                doesn't look like a process number) against ``classe.nome``.
            limit: max results (DataJud caps ``size`` around 10000, but this
                client is for lookups, not bulk export - keep it small).
        """
        index = TRIBUNAL_INDEX[tribunal]
        digits = "".join(ch for ch in query if ch.isdigit())
        if digits and len(digits) >= 15:
            body = {"query": {"match": {"numeroProcesso": digits}}, "size": limit}
        else:
            body = {"query": {"match": {"classe.nome": query}}, "size": limit}
        data = await self._post_search(index, body, category="search")
        hits = (data.get("hits") or {}).get("hits") or []
        return [h.get("_source", {}) for h in hits]

    async def get_processo(self, tribunal: str, numero_processo: str) -> dict:
        """Fetch one docket by its exact ``numeroProcesso`` (CNJ unified number,
        20-25 digits) within one tribunal's DataJud index.
        """
        index = TRIBUNAL_INDEX[tribunal]
        digits = "".join(ch for ch in numero_processo if ch.isdigit())
        body = {"query": {"match": {"numeroProcesso": digits}}, "size": 1}
        data = await self._post_search(index, body, category="act")
        hits = (data.get("hits") or {}).get("hits") or []
        return hits[0].get("_source", {}) if hits else {}
