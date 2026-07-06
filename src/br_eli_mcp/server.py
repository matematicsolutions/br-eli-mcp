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
from .citations import build_citation, parse_proposicao
from .client import DEFAULT_BASE_URL, CamaraClient

INSTRUCTIONS = """\
This MCP server exposes the Camara dos Deputados (Brazilian Chamber of Deputies) open-data API. It tracks the federal legislative PROCESS - bills (proposicoes) as they move through committees and floor votes - not a consolidated database of already-enacted law text.

## Scope and an honest limitation

- **This is not a LexML / URN Lex connector.** LexML documents a URN Lex identifier (Brazil's ELI-equivalent) for consolidated statutes, but no live SRU/OAI-PMH endpoint could be confirmed as of 2026-07 - see DISCOVERY.md. Do not present a `lex_uri` from this server as a consolidated-law citation; it is a stable Camara API URI for the *bill*.
- If a bill's `situacao` reads "Transformada em Norma Juridica" ("Transformed into a legal norm"), the bill passed and became law, but this server does not resolve the resulting statute text - that requires Planalto (no machine-readable API confirmed) or a live LexML endpoint (not yet found).

## Call order

1. `br_search_proposicoes` - list bills of a given `sigla_tipo` (e.g. "PL" = Projeto de Lei) and `ano` (year).
2. `br_get_proposicao` - full detail for one bill by its numeric `id` (from the search results), including its current `situacao` (status).

## Hard constraints

- **No free-text keyword search** - the API filters by type/year/number, not keywords. Use `br_search_proposicoes` to discover candidate `id`s.
- **Every response has `human_readable_citation` + `source_url`** - cite both to the user.
- **Audit log JSONL** - every tool call appends to `~/.matematic/audit/br-eli-mcp.jsonl`.

## Error iteration

Tools return a structured error with a `[code]` prefix:
- `invalid_arg` - a parameter is missing or out of range.
- `not_found` - no bill exists for that id / type+year+number.
- `upstream_error` - a Camara API error (HTTP, timeout). Retry once before surfacing.

## Response style

- Cite bills as `human_readable_citation`: "PL 2597/2024".
- NEVER invent an id, a number or a year - take each from the tool output.
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


def _audit() -> AuditLogger:
    return AuditLogger()


def _map_upstream(exc: Exception) -> Exception:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return ToolError("not_found", "No matching proposicao found in the Camara dos Deputados API.")
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return ToolError("upstream_error", f"Camara API error: {type(exc).__name__}: {exc}")
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


def main() -> None:
    """Run the MCP server over stdio (default for Claude Code)."""
    mcp.run()


if __name__ == "__main__":
    main()
