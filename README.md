# br-eli-mcp

<!-- mcp-name: io.github.matematicsolutions/br-eli-mcp -->

MCP server for the Camara dos Deputados (Brazilian Chamber of Deputies) open-data API
(`dadosabertos.camara.leg.br`). Tracks the federal legislative *process* - bills
(proposicoes) as they move through committees and floor votes.

## What this is not

This is **not** a LexML / URN Lex connector. LexML documents `urn:lex:br:...` as
Brazil's ELI-equivalent identifier for consolidated statutes, but no live
SRU/OAI-PMH endpoint could be confirmed as of 2026-07 (see [DISCOVERY.md](DISCOVERY.md)).
This connector is honest about scope: it gives you a bill's status and a stable
Camara API URI, not a citation to enacted law text.

If you need enacted-law full text, the closest confirmed option today is a
broader project such as [Mcp-Brasil/mcp-brasil](https://github.com/Mcp-Brasil/mcp-brasil)
(MIT), which covers 70 Brazilian government APIs including `datajud` (case law -
requires your own API key, redistribution restricted by CNJ Resolution 446/2022).

## Tools

| Tool | Purpose |
|---|---|
| `br_search_proposicoes` | List bills by type (`PL`, `PLP`, `PEC`, ...) and year |
| `br_get_proposicao` | Full detail + current status for one bill by id |

Bill type codes (`sigla_tipo`), for reference:

| Code | Portuguese | English |
|---|---|---|
| `PL` | Projeto de Lei | ordinary bill |
| `PLP` | Projeto de Lei Complementar | complementary-law bill (implements a constitutional provision) |
| `PEC` | Proposta de Emenda a Constituicao | constitutional amendment proposal |

Every response carries `lex_uri` (Camara's own stable API URI - not a URN Lex),
`human_readable_citation` (e.g. `"PL 2597/2024"`) and `source_url` (public
tramitacao page).

## Install

```bash
pip install br-eli-mcp
```

## Configuration

| Env var | Default |
|---|---|
| `BR_ELI_CACHE_DIR` | `~/.matematic/cache/br-eli` |
| `BR_ELI_AUDIT_DIR` | `~/.matematic/audit` |
| `BR_ELI_BASE_URL` | `https://dadosabertos.camara.leg.br/api/v2` |

## License

Apache-2.0 (code). The Camara dos Deputados open-data API is open data
requiring attribution - see [SOURCES.md](SOURCES.md).
