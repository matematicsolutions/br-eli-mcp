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
from .caselaw_client import TRIBUNAL_INDEX
from .caselaw_client import DEFAULT_BASE_URL as CASELAW_BASE_URL
from .caselaw_client import CaselawClient
from .citations import (
    build_citation,
    build_norma_citation,
    build_processo_citation,
    parse_norma,
    parse_processo,
    parse_proposicao,
)
from .client import DEFAULT_BASE_URL, CamaraClient
from .norma_client import DEFAULT_BASE_URL as NORMA_BASE_URL
from .norma_client import NormaClient
from .norma_text import build_index, extract_text
from .text_client import DEFAULT_BASE_URL as TEXT_BASE_URL
from .text_client import TextClient

INSTRUCTIONS = """\
This MCP server exposes four independent, keyless, no-registration Brazilian open-data APIs:

1. **Camara dos Deputados** - the federal legislative PROCESS: bills (proposicoes) as they move through committees and floor votes.
2. **Congresso Nacional Dados Abertos Legislativos** (legis.senado.leg.br) - the real LexML URN Lex resolver for enacted Normas Juridicas (laws, decrees, constitutional amendments). Confirmed live 2026-07-06 (see DISCOVERY.md "v0.2.0 update") - the v0.1.0 release wrongly reported this as unconfirmed because discovery probed the wrong host (www.lexml.gov.br, which 404s); the real service lives on the Senado's own API gateway.
3. **normas.leg.br** - the full-text companion to (2): a schema.org Legislation tree, one node per Parte/Livro/Titulo/Capitulo/Secao/Artigo, with real article-level text. Confirmed live 2026-07-06 (see DISCOVERY.md "v0.3.0 update") - closes the gap v0.2.0 flagged as unconfirmed.
4. **DataJud CNJ** (api-publica.datajud.cnj.jus.br) - court DOCKET metadata (not ruling text) across STJ/TST/TSE/TRFs/TJs/TRTs/TREs and military courts. Confirmed live 2026-07-06 (see DISCOVERY.md "v0.4.0 update").

## Scope

- `br_get_norma` gives identification, Diario Oficial da Uniao publication provenance, amendment history, and any STF unconstitutionality notes carried in `observacao`.
- `br_get_norma_index` lists the addressable structure of a norma (parts, books, titles, chapters, sections, articles) - use it to find the `dispositivo` suffix (e.g. `"art5"`) for the article you need, rather than guessing one.
- `br_get_norma_texto` returns the real text of one dispositivo (an article and its paragraphs/incisos, concatenated in document order) - not a summary, not a paraphrase.
- If a bill's `situacao` reads "Transformada em Norma Juridica" ("Transformed into a legal norm"), the bill passed and became law - use `br_get_norma` with the resulting URN Lex (if known) to confirm identification, not `br_get_proposicao`.
- `br_search_processos` / `br_get_processo` return a court docket's procedural TIMELINE (`movimentos`: distribuicao, conclusao, publicacao, etc.), parties' classe/assuntos, and the deciding `orgaoJulgador` - **not** the prose text of a ruling. DataJud (the source) carries no ementa/acordao full text. Do not present a `movimento` entry as if it were the holding of a decision - it is a docket event label, at most an inferred outcome signal (e.g. "Provimento em Parte").
- **STF is out of scope** - it does not feed DataJud (confirmed: querying it 404s, by design, not outage) and this server has no STF tool. Do not imply STF coverage.

## Call order

- Legislative process: `br_search_proposicoes` (by `sigla_tipo` + `ano`) then `br_get_proposicao` (by `id`).
- Enacted law identification: `br_get_norma` (by URN Lex, e.g. `urn:lex:br:federal:lei:2002-01-10;10406`). The caller supplies the URN - this tool verifies and enriches it, it does not search by keyword or invent a URN.
- Enacted law text: `br_get_norma_index` (same URN) to find the `dispositivo` suffix, then `br_get_norma_texto` (URN + suffix) for the article text. Do not skip the index step and guess a suffix - `art5` vs `art5_par1u` (paragraph 1) address different text.
- Court docket: `br_search_processos` (by `tribunal` + free-text `query`, e.g. classe name or a CNJ process number) then `br_get_processo` (by `tribunal` + exact `numero_processo`) for the full movement timeline.

## Hard constraints

- **No free-text keyword search** on the legislation APIs - proposicoes filter by type/year/number, normas resolve by URN Lex you already have, dispositivos resolve by suffix from `br_get_norma_index`. `br_search_processos` DOES support free text (classe name or process number) - that is DataJud's own query model, not an exception invented here.
- **Every response has `human_readable_citation` + `source_url`** - cite both to the user.
- **Audit log JSONL** - every tool call appends to `~/.matematic/audit/br-eli-mcp.jsonl`.

## Error iteration

Tools return a structured error with a `[code]` prefix:
- `invalid_arg` - a parameter is missing or out of range (e.g. a URN Lex not matching the `urn:lex:br:...` scheme, or a `tribunal` not in the supported list).
- `not_found` - no bill/norma/dispositivo/processo exists for that id / URN / suffix / numero_processo.
- `upstream_error` - an upstream API error (HTTP, timeout). Retry once before surfacing.

## Response style

- Cite bills as `human_readable_citation`: "PL 2597/2024".
- Cite normas as `human_readable_citation`: the official name/apelido, e.g. "Codigo Civil (2002) (CC)".
- Cite dispositivos as `human_readable_citation`: the article label, e.g. "Art. 5o".
- Cite dockets as `human_readable_citation`: "STJ - Processo <numeroProcesso>".
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


def _audit() -> AuditLogger:
    return AuditLogger()


def _map_upstream(exc: Exception) -> Exception:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return ToolError("not_found", "No matching proposicao found in the Camara dos Deputados API.")
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ToolError("upstream_error", f"Camara API error: {type(exc).__name__}: {exc}")
    return exc


_URN_PREFIX = "urn:lex:br:"


def _map_norma_upstream(exc: Exception) -> Exception:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return ToolError("not_found", "No matching Norma Juridica found for that URN Lex.")
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ToolError("upstream_error", f"legis.senado.leg.br API error: {type(exc).__name__}: {exc}")
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
        raise ToolError("invalid_arg", f"sigla_tipo={sigla_tipo!r} must be a non-empty letters-only code.")
    if not 1823 <= ano <= 2100:
        raise ToolError("invalid_arg", f"ano={ano} is out of range (1823..2100).")
    input_hash = hash_input({"sigla_tipo": sigla_tipo, "ano": ano, "itens": itens})

    with timer() as t:
        try:
            async with CamaraClient(base_url=_base_url()) as client:
                raw_items = await client.search_proposicoes(sigla_tipo.upper(), ano, itens)
        except Exception as exc:
            audit.log(tool="br_search_proposicoes", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms if t.duration_ms else 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_upstream(exc) from exc

    items = [_to_dict(parse_proposicao(r)) for r in raw_items]
    audit.log(tool="br_search_proposicoes", input_hash=input_hash, output_count_or_size=len(items),
              duration_ms=t.duration_ms, status="ok")
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
            audit.log(tool="br_get_proposicao", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms if t.duration_ms else 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_upstream(exc) from exc

    if not raw:
        raise ToolError("not_found", f"No proposicao with id={id}.")
    result = _to_dict(parse_proposicao(raw))
    audit.log(tool="br_get_proposicao", input_hash=input_hash, output_count_or_size=1,
              duration_ms=t.duration_ms, status="ok")
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
        raise ToolError("invalid_arg", f"urn={urn!r} must start with {_URN_PREFIX!r} (LexML URN Lex scheme).")
    input_hash = hash_input({"urn": urn})

    with timer() as t:
        try:
            async with NormaClient(base_url=_norma_base_url()) as client:
                raw = await client.get_norma_by_urn(urn)
        except Exception as exc:
            audit.log(tool="br_get_norma", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms if t.duration_ms else 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_norma_upstream(exc) from exc

    if not raw:
        raise ToolError("not_found", f"No Norma Juridica found for urn={urn!r}.")
    norma = parse_norma(raw, urn)
    citation = build_norma_citation(norma)
    result = {
        **dataclasses.asdict(norma),
        **dataclasses.asdict(citation),
    }
    audit.log(tool="br_get_norma", input_hash=input_hash, output_count_or_size=1,
              duration_ms=t.duration_ms, status="ok")
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
        raise ToolError("invalid_arg", f"urn={urn!r} must start with {_URN_PREFIX!r} (LexML URN Lex scheme).")
    input_hash = hash_input({"urn": urn})

    with timer() as t:
        try:
            async with TextClient(base_url=_text_base_url()) as client:
                tree = await client.get_legislation_tree(urn)
        except Exception as exc:
            audit.log(tool="br_get_norma_index", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms if t.duration_ms else 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_text_upstream(exc) from exc

    if not tree:
        raise ToolError("not_found", f"No Legislation tree found for urn={urn!r}.")
    refs = build_index(tree)
    items = [dataclasses.asdict(r) for r in refs]
    audit.log(tool="br_get_norma_index", input_hash=input_hash, output_count_or_size=len(items),
              duration_ms=t.duration_ms, status="ok")
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
        raise ToolError("invalid_arg", f"urn={urn!r} must start with {_URN_PREFIX!r} (LexML URN Lex scheme).")
    if not dispositivo:
        raise ToolError("invalid_arg", "dispositivo must be a non-empty suffix from br_get_norma_index.")
    input_hash = hash_input({"urn": urn, "dispositivo": dispositivo})

    with timer() as t:
        try:
            async with TextClient(base_url=_text_base_url()) as client:
                tree = await client.get_legislation_tree(urn)
        except Exception as exc:
            audit.log(tool="br_get_norma_texto", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms if t.duration_ms else 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
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
    audit.log(tool="br_get_norma_texto", input_hash=input_hash, output_count_or_size=len(text),
              duration_ms=t.duration_ms, status="ok")
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
            audit.log(tool="br_search_processos", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms if t.duration_ms else 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_caselaw_upstream(exc) from exc

    items = []
    for raw in raw_items:
        processo = parse_processo(raw, tribunal)
        citation = build_processo_citation(processo)
        items.append({**dataclasses.asdict(processo), **dataclasses.asdict(citation)})
    audit.log(tool="br_search_processos", input_hash=input_hash, output_count_or_size=len(items),
              duration_ms=t.duration_ms, status="ok")
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
            audit.log(tool="br_get_processo", input_hash=input_hash, output_count_or_size=0,
                      duration_ms=t.duration_ms if t.duration_ms else 0, status="error",
                      error=f"{type(exc).__name__}: {exc}")
            raise _map_caselaw_upstream(exc) from exc

    if not raw:
        raise ToolError(
            "not_found",
            f"No processo found for tribunal={tribunal!r}, numero_processo={numero_processo!r}.",
        )
    processo = parse_processo(raw, tribunal)
    citation = build_processo_citation(processo)
    result = {**dataclasses.asdict(processo), **dataclasses.asdict(citation)}
    audit.log(tool="br_get_processo", input_hash=input_hash, output_count_or_size=1,
              duration_ms=t.duration_ms, status="ok")
    return result


def main() -> None:
    """Run the MCP server over stdio (default for Claude Code)."""
    mcp.run()


if __name__ == "__main__":
    main()
