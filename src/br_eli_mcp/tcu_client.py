"""Async httpx client for pesquisa.apps.tcu.gov.br - the public REST backend
of the TCU (Tribunal de Contas da Uniao, Brazil's Federal Court of Accounts)
integrated jurisprudence search.

Confirmed live 2026-07-07 (widen round). Discovery path: TCU's open-data
portal (sites.tcu.gov.br/dados-abertos/jurisprudencia/) offers bulk CSVs and
a paginated JSON feed (dados-abertos.apps.tcu.gov.br/api/acordao/
recupera-acordaos) - but that feed's filter parameters silently no-op
(verified live: ano/numero/colegiado all returned the same newest-first
page) and its records carry only the sumario, not ruling text. The search
portal at pesquisa.apps.tcu.gov.br, however, exposes a keyless public REST
backend under ``/rest/publico/`` (path confirmed both in the SPA bundle's
own config and by a browser network trace of a real search):

- ``GET {base}/documentosResumidos?termo=...&quantidade=N&inicio=M``
  free-text search with a dedicated total field ``quantidadeEncontrada``
  (confirmed live: unfiltered total 525,620 acordaos; ``licitação``
  narrows to 53,320) and field-scoped queries
  (``NUMACORDAO:1771 ANOACORDAO:2026 COLEGIADO:"Plenário"`` -> total 1;
  ``KEY:"ACORDAO-COMPLETO-2763173"`` -> total 1).
- ``GET {base}/documento?termo=...&quantidade=1&inicio=0``
  full document: same metadata plus ``ACORDAO`` (the deliberation text),
  ``RELATORIO`` (rapporteur's report) and ``VOTO`` (the vote) as HTML -
  real ruling prose confirmed live (35K+ chars of RELATORIO on the sample
  record), not just the sumario.

**Scope, honestly stated**: a TCU acordao is uniquely identified by
(numero, ano, colegiado) - the same numero/ano recurs across the Plenario
and the two Camaras (confirmed live: ``NUMACORDAO:1771 ANOACORDAO:2026``
alone matched 3 documents, one per colegiado). ``get_acordao`` therefore
reports the match count and this connector's tool layer refuses to guess
which one the caller meant when ``colegiado`` is omitted and more than one
matches.
"""

from __future__ import annotations

import anyio
import httpx

from .cache import HttpCache

DEFAULT_BASE_URL = "https://pesquisa.apps.tcu.gov.br/rest/publico/base/acordao-completo"
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
USER_AGENT = "br-eli-mcp/0.6.0 (+https://github.com/matematicsolutions/br-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3

# The default ordering the real frontend sends (captured live 2026-07-07).
_DEFAULT_ORDENACAO = "DTRELEVANCIA desc, NUMACORDAOINT desc, COPIACOLEGIADO desc,KEY asc"

# Deciding bodies, as spelled in the index's own COLEGIADO field (confirmed
# live on returned records).
COLEGIADOS = ("Plenário", "Primeira Câmara", "Segunda Câmara")


class TcuClient:
    """Async client for the TCU public jurisprudence search backend.

    Use as ``async with TcuClient() as c: ...``.
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

    async def __aenter__(self) -> TcuClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    async def _get(self, path: str, params: dict, *, category: str) -> dict:
        url = f"{self.base_url}/{path}"
        cache_key = "tcu:" + url + ":" + repr(sorted(params.items()))
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

    @staticmethod
    def _escape_term(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    async def search_acordaos(
        self, termo: str, limit: int = 20, inicio: int = 0
    ) -> tuple[int, list[dict]]:
        """Free-text search of TCU acordaos (summaries only - use
        ``get_acordao`` for the ruling text).

        Returns ``(total, documents)`` where ``total`` is the endpoint's own
        dedicated ``quantidadeEncontrada`` field, not a page count. ``termo``
        supports the portal's own field-scoped syntax (e.g.
        ``NUMACORDAO:1771 ANOACORDAO:2026``) in addition to plain words.
        """
        params = {
            "termo": termo,
            "ordenacao": _DEFAULT_ORDENACAO,
            "quantidade": str(limit),
            "inicio": str(inicio),
        }
        data = await self._get("documentosResumidos", params, category="search")
        total = int(data.get("quantidadeEncontrada") or 0)
        return total, data.get("documentos") or []

    def _exact_termo(self, numero: str, ano: str, colegiado: str | None) -> str:
        clauses = [
            f"NUMACORDAO:{self._escape_term(numero)}",
            f"ANOACORDAO:{self._escape_term(ano)}",
        ]
        if colegiado:
            clauses.append(f'COLEGIADO:"{self._escape_term(colegiado)}"')
        return " ".join(clauses)

    async def get_acordao(
        self, numero: str, ano: str, colegiado: str | None = None
    ) -> tuple[int, dict]:
        """Fetch one TCU acordao with full text by (numero, ano[, colegiado]).

        Returns ``(match_count, document)``. ``match_count`` is the index's
        own total for the exact query - when it is > 1 (numero/ano without a
        colegiado matches up to one acordao per deciding body, confirmed
        live), the caller must disambiguate rather than trust the first hit.
        ``document`` is ``{}`` when nothing matches.
        """
        params = {
            "termo": self._exact_termo(numero, ano, colegiado),
            "quantidade": "1",
            "inicio": "0",
        }
        data = await self._get("documento", params, category="act")
        total = int(data.get("quantidadeEncontrada") or 0)
        docs = data.get("documentos") or []
        return total, (docs[0] if docs else {})
