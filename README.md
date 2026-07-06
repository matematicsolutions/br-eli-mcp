# br-eli-mcp

<!-- mcp-name: io.github.matematicsolutions/br-eli-mcp -->

MCP server for two keyless Brazilian open-data APIs:

1. **Camara dos Deputados** (`dadosabertos.camara.leg.br`) - the federal legislative
   *process*: bills (proposicoes) as they move through committees and floor votes.
2. **Congresso Nacional Dados Abertos Legislativos** (`legis.senado.leg.br/dadosabertos`) -
   the real LexML URN Lex resolver for enacted Normas Juridicas (laws, decrees,
   constitutional amendments): identification, Diario Oficial da Uniao publication
   provenance, amendment history, STF unconstitutionality notes.

## What this is (and isn't)

`br_get_norma` resolves a `urn:lex:br:...` against the Senado's own API gateway
(`legis.senado.leg.br/dadosabertos`, public, no key or registration) and returns
identification, publication provenance, and amendment history. It does not return
the full compiled article text (unlike, say, `es_get_text` in es-eli-mcp): no
mechanical rule maps a URN Lex to its Planalto (planalto.gov.br) full-text URL yet,
and fabricating one would risk exactly the citation-hallucination failure mode this
fleet exists to prevent. See [DISCOVERY.md](DISCOVERY.md) for how that endpoint was
found - v0.1.0 had tested the wrong host and wrongly reported it as unconfirmed. If you need
enacted-law full text today, the closest confirmed option is a broader project
such as [Mcp-Brasil/mcp-brasil](https://github.com/Mcp-Brasil/mcp-brasil) (MIT),
which covers 70 Brazilian government APIs including `datajud` (case law - requires
your own API key, redistribution restricted by CNJ Resolution 446/2022).

## Tools

| Tool | Purpose |
|---|---|
| `br_search_proposicoes` | List bills by type (`PL`, `PLP`, `PEC`, ...) and year |
| `br_get_proposicao` | Full detail + current status for one bill by id |
| `br_get_norma` | Resolve an enacted Norma Juridica by URN Lex - identification, DOU provenance, amendment history, STF notes |

Bill type codes (`sigla_tipo`), for reference:

| Code | Portuguese | English |
|---|---|---|
| `PL` | Projeto de Lei | ordinary bill |
| `PLP` | Projeto de Lei Complementar | complementary-law bill (implements a constitutional provision) |
| `PEC` | Proposta de Emenda a Constituicao | constitutional amendment proposal |

Every response carries `lex_uri`, `human_readable_citation` and `source_url`.
For `br_search_proposicoes`/`br_get_proposicao`, `lex_uri` is Camara's own stable
API URI (not a URN Lex - a bill isn't enacted law yet). For `br_get_norma`,
`lex_uri` is the real `urn:lex:br:...` you queried with, e.g.
`"urn:lex:br:federal:lei:2002-01-10;10406"` (Codigo Civil).

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
| `BR_ELI_NORMA_BASE_URL` | `https://legis.senado.leg.br/dadosabertos` |

## License

Apache-2.0 (code). The Camara dos Deputados open-data API is open data
requiring attribution - see [SOURCES.md](SOURCES.md).
