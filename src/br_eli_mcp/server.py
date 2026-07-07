"""FastMCP entry point - Brazilian federal legislative process (Camara dos Deputados) tools.

Run:

    python -m br_eli_mcp.server

Configuration via env:

- ``BR_ELI_CACHE_DIR`` (default ``~/.matematic/cache/br-eli``)
- ``BR_ELI_AUDIT_DIR`` (default ``~/.matematic/audit``)
- ``BR_ELI_BASE_URL`` (default ``https://dadosabertos.camara.leg.br/api/v2``)
"""

from __future__ import annotations

import dataclasses
import os

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .audit import AuditLogger, hash_input, timer
from .carf_client import DEFAULT_BASE_URL as CARF_BASE_URL
from .carf_client import CarfClient
from .caselaw_client import DEFAULT_BASE_URL as CASELAW_BASE_URL
from .caselaw_client import TRIBUNAL_INDEX, CaselawClient
from .citations import (
    build_caso_carf_citation,
    build_caso_stj_citation,
    build_caso_tcu_citation,
    build_caso_tst_citation,
    build_citation,
    build_norma_citation,
    build_processo_citation,
    parse_caso_carf,
    parse_caso_stj,
    parse_caso_tcu,
    parse_caso_tst,
    parse_norma,
    parse_processo,
    parse_proposicao,
)
from .client import DEFAULT_BASE_URL, CamaraClient
from .norma_client import DEFAULT_BASE_URL as NORMA_BASE_URL
from .norma_client import NormaClient
from .norma_text import build_index, extract_text
from .stj_client import DEFAULT_BASE_URL as STJ_BASE_URL
from .stj_client import ORGAO_DATASET, StjClient
from .tcu_client import COLEGIADOS, TcuClient
from .tcu_client import DEFAULT_BASE_URL as TCU_BASE_URL
from .text_client import DEFAULT_BASE_URL as TEXT_BASE_URL
from .text_client import TextClient
from .tst_client import DEFAULT_BASE_URL as TST_BASE_URL
from .tst_client import DOC_TYPES as TST_DOC_TYPES
from .tst_client import TstClient, parse_cnj_numero

INSTRUCTIONS = """\
This MCP server exposes eight independent, keyless, no-registration Brazilian open-data APIs:

1. **Camara dos Deputados** - the federal legislative PROCESS: bills (proposicoes) as they move through committees and floor votes.
2. **Congresso Nacional Dados Abertos Legislativos** (legis.senado.leg.br) - the real LexML URN Lex resolver for enacted Normas Juridicas (laws, decrees, constitutional amendments). Confirmed live 2026-07-06 (see DISCOVERY.md "v0.2.0 update") - the v0.1.0 release wrongly reported this as unconfirmed because discovery probed the wrong host (www.lexml.gov.br, which 404s); the real service lives on the Senado's own API gateway.
3. **normas.leg.br** - the full-text companion to (2): a schema.org Legislation tree, one node per Parte/Livro/Titulo/Capitulo/Secao/Artigo, with real article-level text. Confirmed live 2026-07-06 (see DISCOVERY.md "v0.3.0 update") - closes the gap v0.2.0 flagged as unconfirmed.
4. **DataJud CNJ** (api-publica.datajud.cnj.jus.br) - court DOCKET metadata (not ruling text) across STJ/TST/TSE/TRFs/TJs/TRTs/TREs and military courts. Confirmed live 2026-07-06 (see DISCOVERY.md "v0.4.0 update").
5. **STJ Open Data Portal** (dadosabertos.web.stj.jus.br) - real acordao (ruling) FULL TEXT + ementa (headnote) from the Superior Tribunal de Justica, Brazil's second-highest court. Confirmed live 2026-07-07 (see DISCOVERY.md "v0.5.0 update"). Coverage starts May 2022 - there is no public full-text API for older STJ decisions.
6. **CARF** (acordaos.economia.gov.br) - real acordao (tax ruling) full text from Brazil's federal tax appeals board. Confirmed live 2026-07-07 (see DISCOVERY.md "v0.5.0 update"). Only exact docket/decision-number lookup is supported - free-text search is not reliably indexed upstream (see `carf_client.py` docstring), so this server does not offer a fuzzy CARF search tool.
7. **TST** (jurisprudencia-backend2.tst.jus.br) - real ruling FULL TEXT (inteiro teor) + ementa from the Tribunal Superior do Trabalho, Brazil's labor supreme court. Free-text search AND exact CNJ-process-number lookup both confirmed live 2026-07-07 (v0.6.0 widen round; the v0.5.0 session could not confirm filters because the request body was missing two load-bearing fields - see `tst_client.py` docstring). 3,751,594 acordaos / 8,483,448 documents across all eight types.
8. **TCU** (pesquisa.apps.tcu.gov.br) - real acordao full text (deliberation + rapporteur's report + vote) from the Tribunal de Contas da Uniao, Brazil's Federal Court of Accounts (public-procurement and public-spending jurisprudence). Confirmed live 2026-07-07: 525,620 acordaos, free-text search with a dedicated total field, exact (numero, ano, colegiado) lookup.

## Scope

- `br_get_norma` gives identification, Diario Oficial da Uniao publication provenance, amendment history, and any STF unconstitutionality notes carried in `observacao`.
- `br_get_norma_index` lists the addressable structure of a norma (parts, books, titles, chapters, sections, articles) - use it to find the `dispositivo` suffix (e.g. `"art5"`) for the article you need, rather than guessing one.
- `br_get_norma_texto` returns the real text of one dispositivo (an article and its paragraphs/incisos, concatenated in document order) - not a summary, not a paraphrase.
- If a bill's `situacao` reads "Transformada em Norma Juridica" ("Transformed into a legal norm"), the bill passed and became law - use `br_get_norma` with the resulting URN Lex (if known) to confirm identification, not `br_get_proposicao`.
- `br_search_processos` / `br_get_processo` return a court docket's procedural TIMELINE (`movimentos`: distribuicao, conclusao, publicacao, etc.), parties' classe/assuntos, and the deciding `orgaoJulgador` - **not** the prose text of a ruling. DataJud (the source) carries no ementa/acordao full text. Do not present a `movimento` entry as if it were the holding of a decision - it is a docket event label, at most an inferred outcome signal (e.g. "Provimento em Parte").
- `br_search_case_stj` / `br_get_case_stj` return the real `ementa` (headnote) AND `decisao` (ruling body prose) for STJ acordaos - this DOES carry ruling text, unlike DataJud. Coverage is bounded to the most recent months scanned (see tool docstring) and to May-2022-onwards per the portal's own coverage window - a miss does not mean the case doesn't exist, only that it is outside the scanned window.
- `br_get_case_carf` returns CARF tax-ruling `ementa` and `decisao_texto` by exact `numero_processo` or `numero_decisao` - there is no `br_search_case_carf` free-text tool because CARF's own full-text index is not reliably populated (confirmed empty on live probing for common terms).
- `br_search_case_tst` / `br_get_case_tst` return the real `ementa` AND `inteiro_teor` (full ruling prose) for TST rulings. Search is free text ("contendo as palavras" - quote an expression for exact-phrase); get is by exact CNJ unified process number (NNNNNNN-DD.AAAA.5.TR.OOOO - the fifth segment is 5 for the labor courts). Both confirmed live 2026-07-07.
- `br_search_case_tcu` returns TCU acordao summaries (sumario) with the index's own total; `br_get_case_tcu` returns the real `acordao_texto` (deliberation), `relatorio` (rapporteur's report) and `voto` (vote) prose for one acordao by (numero, ano, colegiado). A numero/ano pair without colegiado can match up to one acordao per deciding body (Plenário / Primeira Câmara / Segunda Câmara) - the tool then errors and lists the matches instead of guessing.
- **STF is out of scope** - it does not feed DataJud (confirmed: querying it 404s, by design, not outage) and this server has no STF tool. Do not imply STF coverage.
- **Planalto (planalto.gov.br) is out of scope** - no confirmed mechanical rule maps a URN Lex to a Planalto URL, and `legislacao.presidencia.gov.br` (REFLEGIS) serves a bot-challenge CAPTCHA page to plain HTTP clients (confirmed live 2026-07-07) rather than a structured API. See DISCOVERY.md.
- **TRF4/TRF5 regional federal courts have no tool here** - both jurisprudence hosts were unreachable from outside Brazil on 2026-07-07 (TCP connections never establish; consistent with geo-blocking). See SOURCES.md.

## Call order

- Legislative process: `br_search_proposicoes` (by `sigla_tipo` + `ano`) then `br_get_proposicao` (by `id`).
- Enacted law identification: `br_get_norma` (by URN Lex, e.g. `urn:lex:br:federal:lei:2002-01-10;10406`). The caller supplies the URN - this tool verifies and enriches it, it does not search by keyword or invent a URN.
- Enacted law text: `br_get_norma_index` (same URN) to find the `dispositivo` suffix, then `br_get_norma_texto` (URN + suffix) for the article text. Do not skip the index step and guess a suffix - `art5` vs `art5_par1u` (paragraph 1) address different text.
- Court docket (metadata only): `br_search_processos` (by `tribunal` + free-text `query`, e.g. classe name or a CNJ process number) then `br_get_processo` (by `tribunal` + exact `numero_processo`) for the full movement timeline.
- STJ ruling text: `br_search_case_stj` (by `orgao` + free text or process number) then `br_get_case_stj` (by `orgao` + exact `numero_processo`) for the full ementa + decisao prose.
- CARF ruling text: `br_get_case_carf` (by exact `numero_processo` or `numero_decisao`) - no search tool, exact lookup only.
- TST ruling text: `br_search_case_tst` (free text, optional `tipo`) then `br_get_case_tst` (by exact CNJ unified process number, e.g. `21036-38.2019.5.04.0021`).
- TCU ruling text: `br_search_case_tcu` (free text or the portal's field-scoped syntax, e.g. `NUMACORDAO:1771 ANOACORDAO:2026`) then `br_get_case_tcu` (by `numero` + `ano`, plus `colegiado` when the pair is ambiguous).

## Hard constraints

- **No free-text keyword search** on the legislation APIs - proposicoes filter by type/year/number, normas resolve by URN Lex you already have, dispositivos resolve by suffix from `br_get_norma_index`. `br_search_processos`, `br_search_case_stj`, `br_search_case_tst` and `br_search_case_tcu` DO support free text - that is each source's own query model, not an exception invented here. CARF has no free-text tool at all (see Scope above).
- **Every response has `human_readable_citation` + `source_url`** - cite both to the user.
- **Audit log JSONL** - every tool call appends to `~/.matematic/audit/br-eli-mcp.jsonl`.

## Error iteration

Tools return a structured error with a `[code]` prefix:
- `invalid_arg` - a parameter is missing or out of range (e.g. a URN Lex not matching the `urn:lex:br:...` scheme, or a `tribunal`/`orgao` not in the supported list).
- `not_found` - no bill/norma/dispositivo/processo/caso exists for that id / URN / suffix / numero_processo.
- `upstream_error` - an upstream API error (HTTP, timeout). Retry once before surfacing.

## Response style

- Cite bills as `human_readable_citation`: "PL 2597/2024".
- Cite normas as `human_readable_citation`: the official name/apelido, e.g. "Codigo Civil (2002) (CC)".
- Cite dispositivos as `human_readable_citation`: the article label, e.g. "Art. 5o".
- Cite dockets as `human_readable_citation`: "STJ - Processo <numeroProcesso>".
- Cite STJ rulings as `human_readable_citation`: "STJ, <classe> <numeroProcesso>, Rel. Min. <nome>, j. DD/MM/AAAA".
- Cite CARF rulings as `human_readable_citation`: "CARF, <turma/camara>, Ac. <numero_decisao>, Rel. <nome>".
- Cite TST rulings as `human_readable_citation`: "TST, <numero_formatado>, Rel. <nome>, <orgao_judicante>".
- Cite TCU rulings as `human_readable_citation`: "TCU, Acórdão <numero>/<ano> - <colegiado>, Rel. <nome>".
- NEVER invent an id, a number, a year, a URN Lex, or a dispositivo suffix - take each from the tool output or the caller's own input.
"""


class ToolError(Exception):
    """Structured error for br-eli MCP tools - visible to the LLM with a [code] prefix."""

    VALID_CODES = frozenset({"invalid_arg", "not_found", "upstream_error"})

    def __init__(self, code: str, message: str):
        if code not in self.VALID_CODES:
            raise ValueError(f"Unknown ToolError code: {code}. Valid: {sorted(self.VALID_CODES)}")
        self.code = code
        super().__init__(f"[{code}] {message}")


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    idempotentHint=True,
    destructiveHint=False,
    openWorldHint=True,
)

mcp: FastMCP = FastMCP(name="br-eli-mcp", instructions=INSTRUCTIONS)


def _base_url() -> str:
    return os.environ.get("BR_ELI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _norma_base_url() -> str:
    return os.environ.get("BR_ELI_NORMA_BASE_URL", NORMA_BASE_URL).rstrip("/")


def _text_base_url() -> str:
    return os.environ.get("BR_ELI_TEXT_BASE_URL", TEXT_BASE_URL).rstrip("/")


def _caselaw_base_url() -> str:
    return os.environ.get("BR_ELI_DATAJUD_BASE_URL", CASELAW_BASE_URL).rstrip("/")


def _stj_base_url() -> str:
    return os.environ.get("BR_ELI_STJ_BASE_URL", STJ_BASE_URL).rstrip("/")


def _carf_base_url() -> str:
    return os.environ.get("BR_ELI_CARF_BASE_URL", CARF_BASE_URL)


def _tst_base_url() -> str:
    return os.environ.get("BR_ELI_TST_BASE_URL", TST_BASE_URL).rstrip("/")


def _tcu_base_url() -> str:
    return os.environ.get("BR_ELI_TCU_BASE_URL", TCU_BASE_URL).rstrip("/")


def _audit() -> AuditLogger:
    return AuditLogger()


def _map_upstream(exc: Exception) -> Exception:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return ToolError(
            "not_found", "No matching proposicao found in the Camara dos Deputados API."
        )
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ToolError("upstream_error", f"Camara API error: {type(exc).__name__}: {exc}")
    return exc


_URN_PREFIX = "urn:lex:br:"


def _map_norma_upstream(exc: Exception) -> Exception:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return ToolError("not_found", "No matching Norma Juridica found for that URN Lex.")
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ToolError(
            "upstream_error", f"legis.senado.leg.br API error: {type(exc).__name__}: {exc}"
        )
    return exc


def _map_text_upstream(exc: Exception) -> Exception:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return ToolError("not_found", "No matching Legislation tree found for that URN Lex.")
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ToolError("upstream_error", f"normas.leg.br API error: {type(exc).__name__}: {exc}")
    return exc


def _map_caselaw_upstream(exc: Exception) -> Exception:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return ToolError("not_found", "No matching tribunal index found in DataJud CNJ.")
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ToolError("upstream_error", f"DataJud CNJ API error: {type(exc).__name__}: {exc}")
    return exc


def _map_stj_upstream(exc: Exception) -> Exception:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return ToolError(
            "not_found", "No matching dataset/resource found on the STJ Open Data portal."
        )
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ToolError("upstream_error", f"STJ Open Data API error: {type(exc).__name__}: {exc}")
    return exc


def _map_carf_upstream(exc: Exception) -> Exception:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return ToolError("not_found", "No matching acordao found in the CARF Solr index.")
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ToolError("upstream_error", f"CARF Solr API error: {type(exc).__name__}: {exc}")
    return exc


def _map_tst_upstream(exc: Exception) -> Exception:
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ToolError(
            "upstream_error", f"TST jurisprudencia API error: {type(exc).__name__}: {exc}"
        )
    return exc


def _map_tcu_upstream(exc: Exception) -> Exception:
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ToolError(
            "upstream_error", f"TCU pesquisa API error: {type(exc).__name__}: {exc}"
        )
    return exc


def _to_dict(p) -> dict:
    citation = build_citation(p)
    return {**dataclasses.asdict(p), **dataclasses.asdict(citation)}


# ---------------------------------------------------------------------------
# br_search_proposicoes
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def br_search_proposicoes(sigla_tipo: str, ano: int, itens: int = 20) -> dict:
    """List Brazilian federal bills (proposicoes) of a given type and year.

    Args:
        sigla_tipo: bill type code, e.g. ``"PL"`` (Projeto de Lei), ``"PLP"``, ``"PEC"``.
        ano: year, e.g. ``2024``.
        itens: max results (default 20, API caps around 100).

    Returns:
        ``{"total": int, "items": [...]}`` - each item carries the citation contract.
    """
    audit = _audit()
    if not sigla_tipo or not sigla_tipo.isalpha():
        raise ToolError(
            "invalid_arg", f"sigla_tipo={sigla_tipo!r} must be a non-empty letters-only code."
        )
    if not 1823 <= ano <= 2100:
        raise ToolError("invalid_arg", f"ano={ano} is out of range (1823..2100).")
    input_hash = hash_input({"sigla_tipo": sigla_tipo, "ano": ano, "itens": itens})

    with timer() as t:
        try:
            async with CamaraClient(base_url=_base_url()) as client:
                raw_items = await client.search_proposicoes(sigla_tipo.upper(), ano, itens)
        except Exception as exc:
            audit.log(
                tool="br_search_proposicoes",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_upstream(exc) from exc

    items = [_to_dict(parse_proposicao(r)) for r in raw_items]
    audit.log(
        tool="br_search_proposicoes",
        input_hash=input_hash,
        output_count_or_size=len(items),
        duration_ms=t.duration_ms,
        status="ok",
    )
    return {"total": len(items), "items": items}


# ---------------------------------------------------------------------------
# br_get_proposicao
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def br_get_proposicao(id: int) -> dict:
    """Fetch full detail (including current status) for one bill by its numeric id.

    Args:
        id: the Camara dos Deputados proposicao id (from ``br_search_proposicoes``).

    Returns:
        A dict with ``sigla_tipo``, ``numero``, ``ano``, ``ementa``, ``situacao``,
        ``lex_uri``, ``human_readable_citation``, ``source_url``.
    """
    audit = _audit()
    if id <= 0:
        raise ToolError("invalid_arg", f"id={id} must be positive.")
    input_hash = hash_input({"id": id})

    with timer() as t:
        try:
            async with CamaraClient(base_url=_base_url()) as client:
                raw = await client.get_proposicao(id)
        except Exception as exc:
            audit.log(
                tool="br_get_proposicao",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_upstream(exc) from exc

    if not raw:
        raise ToolError("not_found", f"No proposicao with id={id}.")
    result = _to_dict(parse_proposicao(raw))
    audit.log(
        tool="br_get_proposicao",
        input_hash=input_hash,
        output_count_or_size=1,
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# br_get_norma
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def br_get_norma(urn: str) -> dict:
    """Resolve a Brazilian Norma Juridica (enacted law/decree/amendment) by its URN Lex.

    Identification + Diario Oficial da Uniao publication provenance + amendment
    history + any STF unconstitutionality notes - NOT the full compiled article
    text (no confirmed URL rule to Planalto; see DISCOVERY.md).

    Args:
        urn: a URN Lex, e.g. ``"urn:lex:br:federal:lei:2002-01-10;10406"``
            (Codigo Civil). Must start with ``"urn:lex:br:"`` - never invent one,
            take it from the user or from another tool's output.

    Returns:
        A dict with ``tipo``, ``numero``, ``norma_nome``, ``apelido``,
        ``data_assinatura``, ``ementa``, ``observacao``, ``amendments``,
        ``lex_uri``, ``human_readable_citation``, ``source_url``.
    """
    audit = _audit()
    if not urn.startswith(_URN_PREFIX):
        raise ToolError(
            "invalid_arg", f"urn={urn!r} must start with {_URN_PREFIX!r} (LexML URN Lex scheme)."
        )
    input_hash = hash_input({"urn": urn})

    with timer() as t:
        try:
            async with NormaClient(base_url=_norma_base_url()) as client:
                raw = await client.get_norma_by_urn(urn)
        except Exception as exc:
            audit.log(
                tool="br_get_norma",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_norma_upstream(exc) from exc

    if not raw:
        raise ToolError("not_found", f"No Norma Juridica found for urn={urn!r}.")
    norma = parse_norma(raw, urn)
    citation = build_norma_citation(norma)
    result = {
        **dataclasses.asdict(norma),
        **dataclasses.asdict(citation),
    }
    audit.log(
        tool="br_get_norma",
        input_hash=input_hash,
        output_count_or_size=1,
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# br_get_norma_index
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def br_get_norma_index(urn: str) -> dict:
    """List the addressable structure of a Norma Juridica: parts, books, titles,
    chapters, sections, and articles, in document order.

    Use this to find the `dispositivo` suffix for the article you need (e.g.
    `"art5"`), then pass it to `br_get_norma_texto` - do not guess a suffix.

    Args:
        urn: a URN Lex, e.g. ``"urn:lex:br:federal:lei:2002-01-10;10406"``
            (Codigo Civil). Must start with ``"urn:lex:br:"``.

    Returns:
        ``{"urn": str, "total": int, "items": [{"suffix", "tipo", "name"}, ...]}``.
    """
    audit = _audit()
    if not urn.startswith(_URN_PREFIX):
        raise ToolError(
            "invalid_arg", f"urn={urn!r} must start with {_URN_PREFIX!r} (LexML URN Lex scheme)."
        )
    input_hash = hash_input({"urn": urn})

    with timer() as t:
        try:
            async with TextClient(base_url=_text_base_url()) as client:
                tree = await client.get_legislation_tree(urn)
        except Exception as exc:
            audit.log(
                tool="br_get_norma_index",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_text_upstream(exc) from exc

    if not tree:
        raise ToolError("not_found", f"No Legislation tree found for urn={urn!r}.")
    refs = build_index(tree)
    items = [dataclasses.asdict(r) for r in refs]
    audit.log(
        tool="br_get_norma_index",
        input_hash=input_hash,
        output_count_or_size=len(items),
        duration_ms=t.duration_ms,
        status="ok",
    )
    return {"urn": urn, "total": len(items), "items": items}


# ---------------------------------------------------------------------------
# br_get_norma_texto
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def br_get_norma_texto(urn: str, dispositivo: str) -> dict:
    """Fetch the real text of one dispositivo (article, or a titulo/capitulo
    header) of a Norma Juridica.

    An article's text includes its caput and every paragraph/inciso/alinea
    beneath it, concatenated in document order - not a summary.

    Args:
        urn: a URN Lex, e.g. ``"urn:lex:br:federal:lei:2002-01-10;10406"``.
        dispositivo: a suffix from `br_get_norma_index`, e.g. ``"art5"``.
            Never guess one - a wrong suffix returns `not_found`, it does not
            silently fall back to a different article.

    Returns:
        A dict with ``dispositivo``, ``text``, ``lex_uri``,
        ``human_readable_citation``, ``source_url``.
    """
    audit = _audit()
    if not urn.startswith(_URN_PREFIX):
        raise ToolError(
            "invalid_arg", f"urn={urn!r} must start with {_URN_PREFIX!r} (LexML URN Lex scheme)."
        )
    if not dispositivo:
        raise ToolError(
            "invalid_arg", "dispositivo must be a non-empty suffix from br_get_norma_index."
        )
    input_hash = hash_input({"urn": urn, "dispositivo": dispositivo})

    with timer() as t:
        try:
            async with TextClient(base_url=_text_base_url()) as client:
                tree = await client.get_legislation_tree(urn)
        except Exception as exc:
            audit.log(
                tool="br_get_norma_texto",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_text_upstream(exc) from exc

    text = extract_text(tree, dispositivo) if tree else None
    if text is None:
        raise ToolError("not_found", f"No dispositivo={dispositivo!r} found for urn={urn!r}.")

    refs = {r.suffix: r for r in build_index(tree)}
    name = refs[dispositivo].name if dispositivo in refs else dispositivo
    lex_uri = f"{urn}!{dispositivo}"
    result = {
        "dispositivo": dispositivo,
        "text": text,
        "lex_uri": lex_uri,
        "human_readable_citation": name or dispositivo,
        "source_url": f"https://normas.leg.br/?urn={lex_uri}",
    }
    audit.log(
        tool="br_get_norma_texto",
        input_hash=input_hash,
        output_count_or_size=len(text),
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# br_search_processos
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def br_search_processos(tribunal: str, query: str, limit: int = 20) -> dict:
    """Search court dockets (procedural metadata, NOT ruling text) in one
    tribunal's DataJud CNJ index.

    DataJud carries classe/assuntos/orgaoJulgador and the full procedural
    timeline (`movimentos`) for each docket - it does not carry the prose
    text of a ruling/acordao/ementa. STF is not covered (see server docstring).

    Args:
        tribunal: one of the supported tribunal codes, e.g. ``"STJ"``,
            ``"TST"``, ``"TRF1"``, ``"TJSP"``, ``"TRT2"``, ``"TRE-SP"``.
        query: free text - a CNJ process number (15+ digits) matches
            `numeroProcesso` exactly; anything else matches `classe.nome`.
        limit: max results (default 20).

    Returns:
        ``{"total": int, "items": [...]}`` - each item carries the citation contract.
    """
    audit = _audit()
    if tribunal not in TRIBUNAL_INDEX:
        raise ToolError(
            "invalid_arg",
            f"tribunal={tribunal!r} is not supported. Known: {sorted(TRIBUNAL_INDEX)}.",
        )
    if not query:
        raise ToolError("invalid_arg", "query must be a non-empty string.")
    input_hash = hash_input({"tribunal": tribunal, "query": query, "limit": limit})

    with timer() as t:
        try:
            async with CaselawClient(base_url=_caselaw_base_url()) as client:
                raw_items = await client.search_processos(tribunal, query, limit)
        except Exception as exc:
            audit.log(
                tool="br_search_processos",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_caselaw_upstream(exc) from exc

    items = []
    for raw in raw_items:
        processo = parse_processo(raw, tribunal)
        citation = build_processo_citation(processo)
        items.append({**dataclasses.asdict(processo), **dataclasses.asdict(citation)})
    audit.log(
        tool="br_search_processos",
        input_hash=input_hash,
        output_count_or_size=len(items),
        duration_ms=t.duration_ms,
        status="ok",
    )
    return {"total": len(items), "items": items}


# ---------------------------------------------------------------------------
# br_get_processo
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def br_get_processo(tribunal: str, numero_processo: str) -> dict:
    """Fetch one court docket by its exact CNJ unified process number.

    Args:
        tribunal: one of the supported tribunal codes, e.g. ``"STJ"``.
        numero_processo: the CNJ unified process number (digits, punctuation
            ignored), e.g. ``"5000035-87.2010.8.21.0057"``.

    Returns:
        A dict with ``numero_processo``, ``classe_nome``, ``orgao_julgador``,
        ``assuntos``, ``movimentos`` (full procedural timeline),
        ``human_readable_citation``, ``source_url``.
    """
    audit = _audit()
    if tribunal not in TRIBUNAL_INDEX:
        raise ToolError(
            "invalid_arg",
            f"tribunal={tribunal!r} is not supported. Known: {sorted(TRIBUNAL_INDEX)}.",
        )
    if not numero_processo:
        raise ToolError("invalid_arg", "numero_processo must be a non-empty string.")
    input_hash = hash_input({"tribunal": tribunal, "numero_processo": numero_processo})

    with timer() as t:
        try:
            async with CaselawClient(base_url=_caselaw_base_url()) as client:
                raw = await client.get_processo(tribunal, numero_processo)
        except Exception as exc:
            audit.log(
                tool="br_get_processo",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_caselaw_upstream(exc) from exc

    if not raw:
        raise ToolError(
            "not_found",
            f"No processo found for tribunal={tribunal!r}, numero_processo={numero_processo!r}.",
        )
    processo = parse_processo(raw, tribunal)
    citation = build_processo_citation(processo)
    result = {**dataclasses.asdict(processo), **dataclasses.asdict(citation)}
    audit.log(
        tool="br_get_processo",
        input_hash=input_hash,
        output_count_or_size=1,
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# br_search_case_stj
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def br_search_case_stj(orgao: str, query: str, limit: int = 20) -> dict:
    """Search STJ (Superior Tribunal de Justica) acordaos - real ruling text.

    Unlike `br_search_processos` (DataJud, metadata only), this returns the
    actual `ementa` (headnote) and `decisao` (ruling body prose) from the
    STJ Open Data Portal. Scans the most recent monthly bulk files for one
    orgao julgador (chamber/section) - a miss means "not in the scanned
    window", not "does not exist". Coverage starts May 2022.

    Args:
        orgao: deciding chamber/section, one of the keys in the supported
            list, e.g. ``"CORTE ESPECIAL"``, ``"TERCEIRA TURMA"``.
        query: free text - a process/registration number (6+ digits) matches
            exactly; anything else matches `ministroRelator` or `ementa`
            (case-insensitive substring).
        limit: max results (default 20).

    Returns:
        ``{"total": int, "items": [...]}`` - each item carries the citation contract.
    """
    audit = _audit()
    orgao_norm = (orgao or "").strip().upper()
    if orgao_norm not in ORGAO_DATASET:
        raise ToolError(
            "invalid_arg",
            f"orgao={orgao!r} is not supported. Known: {sorted(ORGAO_DATASET)}.",
        )
    if not query:
        raise ToolError("invalid_arg", "query must be a non-empty string.")
    input_hash = hash_input({"orgao": orgao_norm, "query": query, "limit": limit})

    with timer() as t:
        try:
            async with StjClient(base_url=_stj_base_url()) as client:
                raw_items = await client.search_casos(orgao_norm, query, limit)
        except Exception as exc:
            audit.log(
                tool="br_search_case_stj",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_stj_upstream(exc) from exc

    items = []
    for raw in raw_items:
        caso = parse_caso_stj(raw, orgao_norm)
        citation = build_caso_stj_citation(caso)
        items.append({**dataclasses.asdict(caso), **dataclasses.asdict(citation)})
    audit.log(
        tool="br_search_case_stj",
        input_hash=input_hash,
        output_count_or_size=len(items),
        duration_ms=t.duration_ms,
        status="ok",
    )
    return {"total": len(items), "items": items}


# ---------------------------------------------------------------------------
# br_get_case_stj
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def br_get_case_stj(orgao: str, numero_processo: str) -> dict:
    """Fetch one STJ acordao by its exact numeroProcesso, with real ruling text.

    Args:
        orgao: deciding chamber/section, e.g. ``"CORTE ESPECIAL"``.
        numero_processo: the STJ process or registration number (digits;
            punctuation ignored).

    Returns:
        A dict with ``ementa``, ``decisao`` (full ruling prose),
        ``ministro_relator``, ``data_decisao``, ``human_readable_citation``,
        ``source_url``.
    """
    audit = _audit()
    orgao_norm = (orgao or "").strip().upper()
    if orgao_norm not in ORGAO_DATASET:
        raise ToolError(
            "invalid_arg",
            f"orgao={orgao!r} is not supported. Known: {sorted(ORGAO_DATASET)}.",
        )
    if not numero_processo:
        raise ToolError("invalid_arg", "numero_processo must be a non-empty string.")
    input_hash = hash_input({"orgao": orgao_norm, "numero_processo": numero_processo})

    with timer() as t:
        try:
            async with StjClient(base_url=_stj_base_url()) as client:
                raw = await client.get_caso(orgao_norm, numero_processo)
        except Exception as exc:
            audit.log(
                tool="br_get_case_stj",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_stj_upstream(exc) from exc

    if not raw:
        raise ToolError(
            "not_found",
            f"No STJ acordao found for orgao={orgao_norm!r}, numero_processo={numero_processo!r} "
            "in the scanned recent months.",
        )
    caso = parse_caso_stj(raw, orgao_norm)
    citation = build_caso_stj_citation(caso)
    result = {**dataclasses.asdict(caso), **dataclasses.asdict(citation)}
    audit.log(
        tool="br_get_case_stj",
        input_hash=input_hash,
        output_count_or_size=1,
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# br_get_case_carf
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def br_get_case_carf(
    numero_processo: str | None = None, numero_decisao: str | None = None
) -> dict:
    """Fetch one CARF (tax appeals) acordao by exact docket or decision number.

    Exactly one of `numero_processo` / `numero_decisao` must be given - this
    is an exact lookup, not a search. There is no free-text search tool for
    CARF because its full-text index is not reliably populated upstream
    (confirmed empty on live probing for common Portuguese terms).

    Args:
        numero_processo: CARF docket number, e.g. ``"16095.000602/2007-70"``.
        numero_decisao: CARF decision number, e.g. ``"9101-002.402"``.

    Returns:
        A dict with ``ementa``, ``decisao_texto`` (full ruling prose),
        ``relator``, ``turma``/``camara``/``secao``, ``data_publicacao``,
        ``human_readable_citation``, ``source_url``.
    """
    audit = _audit()
    if not numero_processo and not numero_decisao:
        raise ToolError("invalid_arg", "Provide numero_processo or numero_decisao.")
    input_hash = hash_input({"numero_processo": numero_processo, "numero_decisao": numero_decisao})

    with timer() as t:
        try:
            async with CarfClient(base_url=_carf_base_url()) as client:
                raw = await client.get_acordao(
                    numero_processo=numero_processo, numero_decisao=numero_decisao
                )
        except Exception as exc:
            audit.log(
                tool="br_get_case_carf",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_carf_upstream(exc) from exc

    if not raw:
        raise ToolError(
            "not_found",
            f"No CARF acordao found for numero_processo={numero_processo!r}, "
            f"numero_decisao={numero_decisao!r}.",
        )
    caso = parse_caso_carf(raw)
    citation = build_caso_carf_citation(caso)
    result = {**dataclasses.asdict(caso), **dataclasses.asdict(citation)}
    audit.log(
        tool="br_get_case_carf",
        input_hash=input_hash,
        output_count_or_size=1,
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# br_search_case_tst
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def br_search_case_tst(query: str, tipo: str = "ACORDAO", limit: int = 20) -> dict:
    """Search TST (labor supreme court) rulings by free text - real ruling text.

    The query goes into the TST frontend's own "contendo as palavras" (AND)
    field - quote an expression for an exact-phrase match, e.g.
    ``"adicional de insalubridade"``. Returns the index's own total plus a
    page of records carrying the real `ementa` and `inteiro_teor` prose.

    Args:
        query: free text (AND semantics; quotes for exact phrase).
        tipo: document type - ``"ACORDAO"`` (default), ``"DESPACHO"``,
            ``"SUM"`` (sumulas), ``"OJ"`` (orientacoes jurisprudenciais),
            ``"PN"``, ``"DESPGP"``, ``"DESPGVP"``, ``"DESPGCG"``.
        limit: max results per page (default 20).

    Returns:
        ``{"total": int, "items": [...]}`` - `total` is the TST index's own
        `totalRegistros` for the whole query, not the page size.
    """
    audit = _audit()
    if not query or not query.strip():
        raise ToolError("invalid_arg", "query must be a non-empty string.")
    if tipo not in TST_DOC_TYPES:
        raise ToolError(
            "invalid_arg", f"tipo={tipo!r} is not supported. Known: {sorted(TST_DOC_TYPES)}."
        )
    input_hash = hash_input({"query": query, "tipo": tipo, "limit": limit})

    with timer() as t:
        try:
            async with TstClient(base_url=_tst_base_url()) as client:
                total, raw_items = await client.search_acordaos(query, tipo=tipo, limit=limit)
        except Exception as exc:
            audit.log(
                tool="br_search_case_tst",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_tst_upstream(exc) from exc

    items = []
    for raw in raw_items:
        caso = parse_caso_tst(raw)
        citation = build_caso_tst_citation(caso)
        items.append({**dataclasses.asdict(caso), **dataclasses.asdict(citation)})
    audit.log(
        tool="br_search_case_tst",
        input_hash=input_hash,
        output_count_or_size=len(items),
        duration_ms=t.duration_ms,
        status="ok",
    )
    return {"total": total, "items": items}


# ---------------------------------------------------------------------------
# br_get_case_tst
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def br_get_case_tst(numero_processo: str, tipo: str = "ACORDAO") -> dict:
    """Fetch one TST ruling by its exact CNJ unified process number - real
    ruling text (`ementa` + `inteiro_teor`).

    Args:
        numero_processo: CNJ unified process number, formatted
            (``"21036-38.2019.5.04.0021"``) or as the raw 20 digits. The
            fifth segment is 5 (Justica do Trabalho) for every TST case.
        tipo: document type (default ``"ACORDAO"``).

    Returns:
        A dict with ``numero_formatado``, ``nome_relator``,
        ``orgao_judicante``, ``data_julgamento``, ``ementa``,
        ``inteiro_teor`` (full ruling prose), ``human_readable_citation``,
        ``source_url``.
    """
    audit = _audit()
    if tipo not in TST_DOC_TYPES:
        raise ToolError(
            "invalid_arg", f"tipo={tipo!r} is not supported. Known: {sorted(TST_DOC_TYPES)}."
        )
    if not numero_processo or parse_cnj_numero(numero_processo) is None:
        raise ToolError(
            "invalid_arg",
            f"numero_processo={numero_processo!r} is not a CNJ unified process number "
            "(NNNNNNN-DD.AAAA.J.TR.OOOO).",
        )
    input_hash = hash_input({"numero_processo": numero_processo, "tipo": tipo})

    with timer() as t:
        try:
            async with TstClient(base_url=_tst_base_url()) as client:
                raw = await client.get_acordao(numero_processo, tipo=tipo)
        except Exception as exc:
            audit.log(
                tool="br_get_case_tst",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_tst_upstream(exc) from exc

    if not raw:
        raise ToolError(
            "not_found",
            f"No TST {tipo} found for numero_processo={numero_processo!r}.",
        )
    caso = parse_caso_tst(raw)
    citation = build_caso_tst_citation(caso)
    result = {**dataclasses.asdict(caso), **dataclasses.asdict(citation)}
    audit.log(
        tool="br_get_case_tst",
        input_hash=input_hash,
        output_count_or_size=1,
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# br_search_case_tcu
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def br_search_case_tcu(query: str, limit: int = 20) -> dict:
    """Search TCU (Federal Court of Accounts) acordaos - public-procurement
    and public-spending jurisprudence.

    Returns summaries (`sumario`) plus the index's own total. Use
    `br_get_case_tcu` for the full ruling text of one acordao. The query
    supports the portal's own field-scoped syntax in addition to plain
    words, e.g. ``NUMACORDAO:1771 ANOACORDAO:2026``.

    Args:
        query: free text or field-scoped query.
        limit: max results (default 20).

    Returns:
        ``{"total": int, "items": [...]}`` - `total` is the TCU index's own
        `quantidadeEncontrada` for the whole query, not the page size.
    """
    audit = _audit()
    if not query or not query.strip():
        raise ToolError("invalid_arg", "query must be a non-empty string.")
    input_hash = hash_input({"query": query, "limit": limit})

    with timer() as t:
        try:
            async with TcuClient(base_url=_tcu_base_url()) as client:
                total, raw_items = await client.search_acordaos(query, limit=limit)
        except Exception as exc:
            audit.log(
                tool="br_search_case_tcu",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_tcu_upstream(exc) from exc

    items = []
    for raw in raw_items:
        caso = parse_caso_tcu(raw)
        citation = build_caso_tcu_citation(caso)
        items.append({**dataclasses.asdict(caso), **dataclasses.asdict(citation)})
    audit.log(
        tool="br_search_case_tcu",
        input_hash=input_hash,
        output_count_or_size=len(items),
        duration_ms=t.duration_ms,
        status="ok",
    )
    return {"total": total, "items": items}


# ---------------------------------------------------------------------------
# br_get_case_tcu
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def br_get_case_tcu(numero: str, ano: str, colegiado: str | None = None) -> dict:
    """Fetch one TCU acordao with the real ruling text: `acordao_texto`
    (deliberation), `relatorio` (rapporteur's report) and `voto` (vote).

    A TCU acordao is uniquely identified by (numero, ano, colegiado) - the
    same numero/ano recurs across the Plenario and the two Camaras. When
    `colegiado` is omitted and more than one acordao matches, this errors
    and lists the matching bodies instead of guessing.

    Args:
        numero: acordao number, e.g. ``"1771"``.
        ano: four-digit year, e.g. ``"2026"``.
        colegiado: deciding body - ``"Plenário"``, ``"Primeira Câmara"`` or
            ``"Segunda Câmara"`` (accent-sensitive, as spelled in the index).

    Returns:
        A dict with ``numero``, ``ano``, ``colegiado``, ``relator``,
        ``data_sessao``, ``sumario``, ``acordao_texto``, ``relatorio``,
        ``voto``, ``human_readable_citation``, ``source_url``.
    """
    audit = _audit()
    if not numero or not numero.strip().isdigit():
        raise ToolError("invalid_arg", f"numero={numero!r} must be a number, e.g. '1771'.")
    if not ano or not (ano.strip().isdigit() and len(ano.strip()) == 4):
        raise ToolError("invalid_arg", f"ano={ano!r} must be a four-digit year, e.g. '2026'.")
    if colegiado is not None and colegiado not in COLEGIADOS:
        raise ToolError(
            "invalid_arg",
            f"colegiado={colegiado!r} is not supported. Known: {list(COLEGIADOS)}.",
        )
    input_hash = hash_input({"numero": numero, "ano": ano, "colegiado": colegiado})

    with timer() as t:
        try:
            async with TcuClient(base_url=_tcu_base_url()) as client:
                match_count, raw = await client.get_acordao(
                    numero.strip(), ano.strip(), colegiado
                )
        except Exception as exc:
            audit.log(
                tool="br_get_case_tcu",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_tcu_upstream(exc) from exc

    if match_count == 0 or not raw:
        raise ToolError(
            "not_found",
            f"No TCU acordao found for numero={numero!r}, ano={ano!r}, "
            f"colegiado={colegiado!r}.",
        )
    if match_count > 1:
        raise ToolError(
            "invalid_arg",
            f"Acórdão {numero}/{ano} matches {match_count} documents (one per deciding "
            f"body). Pass colegiado - one of {list(COLEGIADOS)} - to disambiguate.",
        )
    caso = parse_caso_tcu(raw)
    citation = build_caso_tcu_citation(caso)
    result = {**dataclasses.asdict(caso), **dataclasses.asdict(citation)}
    audit.log(
        tool="br_get_case_tcu",
        input_hash=input_hash,
        output_count_or_size=1,
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


def main() -> None:
    """Run the MCP server over stdio (default for Claude Code)."""
    mcp.run()


if __name__ == "__main__":
    main()
