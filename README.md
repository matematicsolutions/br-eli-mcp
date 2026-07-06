# br-eli-mcp

<!-- mcp-name: io.github.matematicsolutions/br-eli-mcp -->

MCP server for three keyless Brazilian open-data APIs:

1. **Camara dos Deputados** (`dadosabertos.camara.leg.br`) - the federal legislative
   *process*: bills (proposicoes) as they move through committees and floor votes.
2. **Congresso Nacional Dados Abertos Legislativos** (`legis.senado.leg.br/dadosabertos`) -
   the real LexML URN Lex resolver for enacted Normas Juridicas (laws, decrees,
   constitutional amendments): identification, Diario Oficial da Uniao publication
   provenance, amendment history, STF unconstitutionality notes.
3. **normas.leg.br** - the full-text companion to (2): real article-by-article text of
   enacted legislation, addressed by the same URN Lex.

## What this is (and isn't)

`br_get_norma` resolves a `urn:lex:br:...` against the Senado's own API gateway
(public, no key or registration) and returns identification, publication provenance,
and amendment history. `br_get_norma_index` + `br_get_norma_texto` resolve the same
URN against `normas.leg.br`'s structured Legislation tree for the real text of one
article - not a summary. See [DISCOVERY.md](DISCOVERY.md) for how both endpoints were
found: v0.1.0 tested the wrong host for identification and wrongly reported it as
unconfirmed; v0.2.0 fixed that but still lacked full text; v0.3.0 found the
full-text API on the same domain as the human-readable citation page.

This connector does not scrape Planalto (planalto.gov.br) HTML - no confirmed
mechanical rule maps a URN Lex to a Planalto URL for every act type, and fabricating
one would risk the citation-hallucination failure mode this fleet exists to prevent.
A minority of act types (mostly decrees) have no inline text in `normas.leg.br` either;
for those, or for case law (`datajud` - requires your own API key, redistribution
restricted by CNJ Resolution 446/2022), see the broader
[Mcp-Brasil/mcp-brasil](https://github.com/Mcp-Brasil/mcp-brasil) (MIT) project.

## Tools

| Tool | Purpose |
|---|---|
| `br_search_proposicoes` | List bills by type (`PL`, `PLP`, `PEC`, ...) and year |
| `br_get_proposicao` | Full detail + current status for one bill by id |
| `br_get_norma` | Resolve an enacted Norma Juridica by URN Lex - identification, DOU provenance, amendment history, STF notes |
| `br_get_norma_index` | List the addressable structure of a Norma (parts, books, titles, chapters, sections, articles) |
| `br_get_norma_texto` | Fetch the real text of one article (dispositivo) of a Norma |

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
`"urn:lex:br:federal:lei:2002-01-10;10406"` (Codigo Civil). For `br_get_norma_texto`,
`lex_uri` is that URN plus the article suffix, e.g. `"...;10406!art5"`.

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
| `BR_ELI_TEXT_BASE_URL` | `https://normas.leg.br/api/public` |

## License

Apache-2.0 (code). The Camara dos Deputados open-data API is open data
requiring attribution - see [SOURCES.md](SOURCES.md).
