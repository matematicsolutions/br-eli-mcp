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
from .citations import build_citation, build_norma_citation, parse_norma, parse_proposicao
from .client import DEFAULT_BASE_URL, CamaraClient
from .norma_client import DEFAULT_BASE_URL as NORMA_BASE_URL
from .norma_client import NormaClient

INSTRUCTIONS = """\
This MCP server exposes two independent, keyless, no-registration Brazilian open-data APIs:

1. **Camara dos Deputados** - the federal legislative PROCESS: bills (proposicoes) as they move through committees and floor votes.
2. **Congresso Nacional Dados Abertos Legislativos** (legis.senado.leg.br) - the real LexML URN Lex resolver for enacted Normas Juridicas (laws, decrees, constitutional amendments). Confirmed live 2026-07-06 (see DISCOVERY.md "v0.2.0 update") - the v0.1.0 release wrongly reported this as unconfirmed because discovery probed the wrong host (www.lexml.gov.br, which 404s); the real service lives on the Senado's own API gateway.

## Scope and an honest limitation

- `br_get_norma` gives you the Norma's identification, official publication (Diario Oficial da Uniao) provenance, amendment history, and any STF unconstitutionality notes carried in `observacao` - but **not the full compiled article text**. No mechanical URL rule from a URN Lex to a Planalto (planalto.gov.br) full-text page could be confirmed as of 2026-07 - do not fabricate one. Point the lawyer to `source_url` (normas.leg.br) for the human-readable rendering, or planalto.gov.br if named in `observacao`/general knowledge.
- If a bill's `situacao` reads "Transformada em Norma Juridica" ("Transformed into a legal norm"), the bill passed and became law - use `br_get_norma` with the resulting URN Lex (if known) to confirm identification, not `br_get_proposicao`.

## Call order

- Legislative process: `br_search_proposicoes` (by `sigla_tipo` + `ano`) then `br_get_proposicao` (by `id`).
- Enacted law identification: `br_get_norma` (by URN Lex, e.g. `urn:lex:br:federal:lei:2002-01-10;10406`). The caller supplies the URN - this tool verifies and enriches it, it does not search by keyword or invent a URN.

## Hard constraints

- **No free-text keyword search** on either API - proposicoes filter by type/year/number, normas resolve by URN Lex you already have.
- **Every response has `human_readable_citation` + `source_url`** - cite both to the user.
- **Audit log JSONL** - every tool call appends to `~/.matematic/audit/br-eli-mcp.jsonl`.

## Error iteration

Tools return a structured error with a `[code]` prefix:
- `invalid_arg` - a parameter is missing or out of range (e.g. a URN Lex not matching the `urn:lex:br:...` scheme).
- `not_found` - no bill/norma exists for that id / URN.
- `upstream_error` - an upstream API error (HTTP, timeout). Retry once before surfacing.

## Response style

- Cite bills as `human_readable_citation`: "PL 2597/2024".
- Cite normas as `human_readable_citation`: the official name/apelido, e.g. "Codigo Civil (2002) (CC)".
- NEVER invent an id, a number, a year, or a URN Lex - take each from the tool output or the caller's own input.
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


def main() -> None:
    """Run the MCP server over stdio (default for Claude Code)."""
    mcp.run()


if __name__ == "__main__":
    main()
