# br-eli-mcp

<!-- mcp-name: io.github.matematicsolutions/br-eli-mcp -->

MCP server for six keyless, no-registration Brazilian open-data APIs:

1. **Camara dos Deputados** (`dadosabertos.camara.leg.br`) - the federal legislative
   *process*: bills (proposicoes) as they move through committees and floor votes.
2. **Congresso Nacional Dados Abertos Legislativos** (`legis.senado.leg.br/dadosabertos`) -
   the real LexML URN Lex resolver for enacted Normas Juridicas (laws, decrees,
   constitutional amendments): identification, Diario Oficial da Uniao publication
   provenance, amendment history, STF unconstitutionality notes.
3. **normas.leg.br** - the full-text companion to (2): real article-by-article text of
   enacted legislation, addressed by the same URN Lex.
4. **DataJud CNJ** (`api-publica.datajud.cnj.jus.br`) - court DOCKET metadata (not
   ruling text) across STJ/TST/TSE/TRFs/TJs/TRTs/TREs and military courts.
5. **STJ Open Data Portal** (`dadosabertos.web.stj.jus.br`) - real acordao (ruling)
   full text + ementa (headnote) from the Superior Tribunal de Justica, Brazil's
   second-highest court. Coverage starts May 2022.
6. **CARF** (`acordaos.economia.gov.br`) - real acordao (tax ruling) full text from
   Brazil's federal tax appeals board, by exact docket/decision number.

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
Re-verified live 2026-07-07: `legislacao.presidencia.gov.br` (the REFLEGIS portal
the manifest names) does not return a plain HTTP response to a keyless client at
all - the connection is accepted but the request times out with zero bytes
received, consistent with a bot-challenge/WAF in front of it, not a structured API.
A minority of act types (mostly decrees) have no inline text in `normas.leg.br`
either; for those, see [DISCOVERY.md](DISCOVERY.md).

For case law, DataJud (docket metadata only, requires your own API key,
redistribution restricted by CNJ Resolution 446/2022), the STJ Open Data Portal
(real acordao text, May 2022+), and CARF (real tax-ruling text, exact lookup only)
are wired in below. TST has a confirmed-live real backend
(`jurisprudencia-backend2.tst.jus.br`, found via the frontend's own
`config.json`) that returns real ruling text with a working document-type
filter and pagination - but no exact-match/process-number lookup could be
confirmed live (every reverse-engineered filter field left the result count
unchanged), so this release ships no TST tool rather than one that silently
can't find a specific case. See [DISCOVERY.md](DISCOVERY.md) for the exact
probes run and the confirmed request/response contract.

## Tools

| Tool | Purpose |
|---|---|
| `br_search_proposicoes` | List bills by type (`PL`, `PLP`, `PEC`, ...) and year |
| `br_get_proposicao` | Full detail + current status for one bill by id |
| `br_get_norma` | Resolve an enacted Norma Juridica by URN Lex - identification, DOU provenance, amendment history, STF notes |
| `br_get_norma_index` | List the addressable structure of a Norma (parts, books, titles, chapters, sections, articles) |
| `br_get_norma_texto` | Fetch the real text of one article (dispositivo) of a Norma |
| `br_search_processos` | Search court dockets (metadata only) in one tribunal's DataJud CNJ index |
| `br_get_processo` | Fetch one court docket by exact CNJ unified process number |
| `br_search_case_stj` | Search STJ acordaos (real ruling text) by process number or free text |
| `br_get_case_stj` | Fetch one STJ acordao by exact process number - ementa + ruling body text |
| `br_get_case_carf` | Fetch one CARF tax acordao by exact docket or decision number - ementa + ruling body text |

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
| `BR_ELI_DATAJUD_BASE_URL` | `https://api-publica.datajud.cnj.jus.br` |
| `BR_ELI_STJ_BASE_URL` | `https://dadosabertos.web.stj.jus.br` |
| `BR_ELI_CARF_BASE_URL` | `https://acordaos.economia.gov.br/solr/acordaos2/select` |

## License

Apache-2.0 (code). The Camara dos Deputados open-data API is open data
requiring attribution - see [SOURCES.md](SOURCES.md).
