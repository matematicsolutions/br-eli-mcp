# Sources

## Camara dos Deputados open data (`dadosabertos.camara.leg.br`)

- **Origin**: Camara dos Deputados (Brazilian Chamber of Deputies)
- **License**: open data, attribution required, low legal risk. Verified against
  [Mcp-Brasil/mcp-brasil SOURCES.md](https://github.com/Mcp-Brasil/mcp-brasil/blob/main/SOURCES.md)
  (`Legislativo (Camara, Senado) | Baixo | Open data; atribuicao`).
- **Access**: keyless REST, JSON.
- **Coverage**: this connector only calls `/proposicoes` (list + detail). It does
  not cover Senado, votacoes, deputados, or any other Camara/Senado endpoint.

## Congresso Nacional Dados Abertos Legislativos (`legis.senado.leg.br/dadosabertos`)

- **Origin**: Senado Federal / Congresso Nacional.
- **License**: public open data, "acesso publico, sem necessidade de autenticacao"
  (stated in the API's own OpenAPI spec) - no key, no registration.
- **Access**: keyless REST, JSON (`Accept: application/json`) or XML. Rate limit
  10 req/s (HTTP 429 above that), enforced upstream.
- **Coverage**: this connector only calls `/legislacao/urn` (identification,
  publication provenance, amendment history for one Norma Juridica by URN Lex).
- **Discovery note**: v0.1.0 tested the wrong host (`www.lexml.gov.br`) and wrongly
  reported no live endpoint. See DISCOVERY.md.

## normas.leg.br (`normas.leg.br/api/public`)

- **Origin**: same LexML/Congresso Nacional data, republished as a schema.org
  `Legislation` JSON-LD tree with real article-by-article text.
- **License**: same public-data status as the Senado API above (same underlying
  government source, different presentation).
- **Access**: keyless REST, JSON.
- **Coverage**: this connector only calls `/normas` (full Legislation tree for one
  URN Lex). Confirmed to carry inline text for laws (`LEI`, `LCP`) and constitutional
  amendments; a minority of act types (mostly decrees, `DEC`/`MPV`) may lack inline
  text - not handled by this connector (see "Not covered" below).

## Not covered (out of scope for this connector)

- **DataJud/CNJ** (case law) - Resolucao CNJ 331/2020 and 446/2022 require your own
  API key and **forbid bulk redistribution**. Any future connector needs a
  bring-your-own-key model (like `fr-eli-mcp`'s PISTE OAuth), not bulk hosting.
- **Planalto** (`planalto.gov.br`) - the primary official publication site. This
  connector deliberately does not scrape its HTML: no confirmed mechanical rule
  maps a URN Lex to a Planalto URL for every act type, and `normas.leg.br` already
  covers the act types (laws, constitutional amendments) with the best full-text
  coverage. See DISCOVERY.md for the acts where Planalto scraping would still be
  the only option (decrees, provisional measures).
