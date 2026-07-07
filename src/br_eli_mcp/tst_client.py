"""Async httpx client for jurisprudencia-backend2.tst.jus.br - the real
backend behind the TST (Tribunal Superior do Trabalho) jurisprudencia search
frontend at https://jurisprudencia.tst.jus.br/.

Confirmed live 2026-07-07 (v0.5.0 discovery): the frontend is a React SPA
that reads its API base URL from a runtime ``/config.json`` (``base_url``
key), then POSTs to ``{base_url}/rest/pesquisa-textual/{start}/{size}``.

**v0.6.0 update - exact-match lookup now CONFIRMED.** The v0.5.0 session
reverse-engineered filter field names from the minified frontend bundle and
found every one of them a silent no-op, so no TST tool was shipped. This
widen round captured the REAL request body via a browser network trace of
the live frontend (the exact remediation v0.5.0's notes called for), and
the difference is two fields the static analysis missed:

- a top-level ``"orgao": "TST"``;
- ``numeracaoUnica.orgao`` defaulting to ``"5"`` (the Justica do Trabalho
  segment of the CNJ unified numbering) even when no number is queried.

With the full captured shape, replayed from a bare httpx client (no cookies,
no CSRF header), the filters demonstrably work - confirmed live 2026-07-07:

- baseline ``tipos=["ACORDAO"]``: 3,751,594 records (``totalRegistros``,
  the endpoint's own dedicated total field);
- free text ``e='"adicional de insalubridade"'``: narrows to 228,802;
- full ``numeracaoUnica`` for AIRR 21036-38.2019.5.04.0021 (a record the
  endpoint itself returned): ``totalRegistros == 1``, and the single record
  returned is that exact case;
- partial ``numeracaoUnica`` (numero only): 41 candidates - the filter
  composes, it is not an all-or-nothing match.

**Document-type gotcha, confirmed live**: the valid ``tipos`` codes are the
eight the real frontend sends (see ``DOC_TYPES``), each verified to change
``totalRegistros``. ``DECISAO_MONOCRATICA`` - listed in the frontend's own
``config.json`` and trusted by v0.5.0 - is NOT one of them: the backend
silently ignores it and returns the full 8,483,448-document corpus. Unknown
codes no-op rather than erroring, so this client whitelists ``DOC_TYPES``
and rejects anything else instead of passing values through.
"""

from __future__ import annotations

import re

import anyio
import httpx

from .cache import HttpCache

DEFAULT_BASE_URL = "https://jurisprudencia-backend2.tst.jus.br"
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
USER_AGENT = "br-eli-mcp/0.6.0 (+https://github.com/matematicsolutions/br-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3

# The eight document-type codes the real frontend sends, captured live from a
# browser network trace 2026-07-07 and each individually verified to change
# totalRegistros (ACORDAO 3,751,594 / DESPACHO 4,730,562 / SUM 463 / PN 120 /
# OJ 709 / DESPGP 505,319 / DESPGVP 882,597 / DESPGCG 9,037). Do NOT add
# codes from config.json without the same per-code verification - the backend
# silently no-ops unknown codes (see module docstring).
DOC_TYPES = frozenset(
    {"ACORDAO", "DESPACHO", "SUM", "PN", "OJ", "DESPGP", "DESPGVP", "DESPGCG"}
)

# CNJ unified process number: NNNNNNN-DD.AAAA.J.TR.OOOO
_CNJ_RE = re.compile(r"^(\d{1,7})-?(\d{2})\.?(\d{4})\.?(\d)\.?(\d{2})\.?(\d{4})$")


def parse_cnj_numero(numero_processo: str) -> dict[str, str] | None:
    """Parse a CNJ unified process number into ``numeracaoUnica`` parts.

    Accepts the formatted form (``21036-38.2019.5.04.0021``), the same with
    punctuation stripped, or the raw 20-digit form
    (``00210363820195040021``). Returns ``None`` when the input is not a
    CNJ unified number - never guesses a partial match.
    """
    value = numero_processo.strip()
    digits = re.sub(r"\D", "", value)
    if len(digits) == 20:
        return {
            "numero": digits[0:7],
            "digito": digits[7:9],
            "ano": digits[9:13],
            "orgao": digits[13],
            "tribunal": digits[14:16],
            "vara": digits[16:20],
        }
    m = _CNJ_RE.match(value)
    if m:
        numero, digito, ano, orgao, tribunal, vara = m.groups()
        return {
            "numero": numero,
            "digito": digito,
            "ano": ano,
            "orgao": orgao,
            "tribunal": tribunal,
            "vara": vara,
        }
    return None


def _request_body(
    *,
    e: str | None = None,
    numeracao: dict[str, str] | None = None,
    tipos: list[str] | None = None,
) -> dict:
    """Build the exact request shape the real frontend sends (captured live
    2026-07-07). The top-level ``orgao`` and the ``numeracaoUnica.orgao``
    default of ``"5"`` are load-bearing - without them the backend silently
    ignores every filter (the v0.5.0 failure mode).
    """
    numeracao_unica: dict[str, str | None] = {
        "numero": None,
        "digito": None,
        "ano": None,
        "orgao": "5",
        "tribunal": None,
        "vara": None,
    }
    if numeracao:
        numeracao_unica.update(numeracao)
    return {
        "ou": None,
        "e": e,
        "termoExato": "",
        "naoContem": None,
        "ementa": None,
        "dispositivo": None,
        "numeracaoUnica": numeracao_unica,
        "orgaosJudicantes": [],
        "ministros": [],
        "convocados": [],
        "classesProcessuais": [],
        "indicadores": [],
        "assuntos": [],
        "tipos": tipos or ["ACORDAO"],
        "orgao": "TST",
    }


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
        cache_key = "tst:" + url + ":" + repr(sorted(body.items(), key=repr))
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

    async def search_acordaos(
        self, query: str, tipo: str = "ACORDAO", page: int = 1, limit: int = 20
    ) -> tuple[int, list[dict]]:
        """Free-text search of TST rulings, filtered by document ``tipo``.

        ``query`` goes into the frontend's own ``e`` ("contendo as palavras")
        field - confirmed live to narrow the result count (see module
        docstring). Quote an expression for an exact-phrase match, exactly
        as the human frontend documents.

        Returns ``(total, records)`` where ``total`` is the endpoint's own
        ``totalRegistros`` field - a dedicated total, not a page count.
        """
        if tipo not in DOC_TYPES:
            raise ValueError(f"tipo={tipo!r} is not a confirmed TST doc type: {sorted(DOC_TYPES)}")
        start = (page - 1) * limit + 1
        body = _request_body(e=query, tipos=[tipo])
        data = await self._post_page(start, limit, body, category="search")
        total = int(data.get("totalRegistros") or 0)
        registros = data.get("registros") or []
        return total, [r.get("registro", {}) for r in registros if isinstance(r, dict)]

    async def get_acordao(self, numero_processo: str, tipo: str = "ACORDAO") -> dict:
        """Fetch one TST ruling by its exact CNJ unified process number.

        Confirmed live 2026-07-07: a fully-populated ``numeracaoUnica``
        narrows ``totalRegistros`` to exactly the matching case (see module
        docstring for the probe). Returns ``{}`` when no record matches -
        it never falls back to a partial or fuzzy match.
        """
        if tipo not in DOC_TYPES:
            raise ValueError(f"tipo={tipo!r} is not a confirmed TST doc type: {sorted(DOC_TYPES)}")
        numeracao = parse_cnj_numero(numero_processo)
        if numeracao is None:
            raise ValueError(
                f"numero_processo={numero_processo!r} is not a CNJ unified process number "
                "(NNNNNNN-DD.AAAA.J.TR.OOOO)."
            )
        body = _request_body(numeracao=numeracao, tipos=[tipo])
        data = await self._post_page(1, 2, body, category="act")
        registros = data.get("registros") or []
        records = [r.get("registro", {}) for r in registros if isinstance(r, dict)]
        return records[0] if records else {}
