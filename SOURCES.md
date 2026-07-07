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

## DataJud CNJ (`api-publica.datajud.cnj.jus.br`)

- **Origin**: Conselho Nacional de Justica (CNJ) - the unified public API across
  91 Brazilian courts (state, federal, labor, electoral, military).
- **License**: public, keyless (a single shared publicly-documented API key, not
  per-developer registration). **Resolucao CNJ 446/2022 forbids bulk
  redistribution** - this connector only does live, per-query lookups, never
  bulk-hosts data.
- **Access**: keyless-to-the-caller REST/Elasticsearch DSL, JSON.
- **Coverage**: docket/procedural metadata only (`classe`, `assuntos`,
  `orgaoJulgador`, `movimentos`) - **no ruling text field exists** in this API.
  STF is not covered (not indexed by DataJud).

## STJ Open Data Portal (`dadosabertos.web.stj.jus.br`)

- **Origin**: Superior Tribunal de Justica (STJ), Brazil's second-highest court.
- **License**: Open Government Data (CKAN portal, CC-BY per dataset metadata).
- **Access**: keyless CKAN REST (`package_show` to list monthly resource files)
  plus plain HTTPS GET of each dated bulk JSON file. Not a per-case query
  endpoint - this connector scans a bounded number of the most recent monthly
  files in-memory per query (see `stj_client.py`).
- **Coverage**: real acordao (ruling) full prose text (`decisao`) and ementa
  (headnote), plus relator/classe/dates - confirmed live 2026-07-07. Coverage
  starts May 2022 ("espelhos data from May 2022 onwards" per the portal's own
  CKAN dataset notes) - **no public full-text API exists for pre-2022 STJ
  decisions** on this portal.

## CARF (`acordaos.economia.gov.br`)

- **Origin**: Conselho Administrativo de Recursos Fiscais (CARF), Brazil's
  federal tax appeals board (Ministerio da Fazenda).
- **License**: Open Government Data.
- **Access**: keyless, public Apache Solr index (`/solr/acordaos2/select`), no
  registration. Confirmed live 2026-07-07: ~579K acordaos indexed.
- **Coverage**: real ruling text (`decisao_txt`) and ementa (`ementa_s`), plus
  docket number, decision number, relator, collegiate body, and session/
  publication dates. **Exact-field lookup only** (`numero_processo_s` /
  `numero_decisao_s`) - the free-text field (`conteudo_txt`) returned zero hits
  for common Portuguese terms during live probing (the manifest's own upstream
  notes flag the same gap), so this connector does not offer a fuzzy CARF
  search tool, only `br_get_case_carf`. The acordao PDF URL (`lex_uri`/
  `source_url`) is confirmed live 2026-07-07: each Solr record's own
  `nome_arquivo_pdf_s` field (the API's own data, not a guess) resolves under
  `https://acordaos.economia.gov.br/acordaos2/pdfs/processados/<that filename>`
  - fetching the constructed URL for a real record returned HTTP 200 with a
  real PDF body (898,936 bytes for the sample record checked). This falls back
  to the Solr search endpoint only if a record is missing that field.

## Not covered (out of scope for this connector)

- **Planalto** (`planalto.gov.br`) - the primary official publication site. This
  connector deliberately does not scrape its HTML: no confirmed mechanical rule
  maps a URN Lex to a Planalto URL for every act type, and `normas.leg.br` already
  covers the act types (laws, constitutional amendments) with the best full-text
  coverage. Re-checked live 2026-07-07: `legislacao.presidencia.gov.br` (REFLEGIS,
  the URL the `worldwidelaw/legal-sources` manifest names for `BR/Planalto`)
  accepts a TCP/TLS connection but never returns an HTTP response to a plain
  client within a generous timeout - consistent with a bot-challenge/WAF, not a
  structured API. See DISCOVERY.md for the acts where Planalto scraping would
  still be the only option (decrees, provisional measures) if this is revisited
  with a browser-automation approach (out of scope for this connector's
  keyless-HTTP-only architecture).
## TST (`jurisprudencia-backend2.tst.jus.br`) - confirmed live, NOT wired into a tool this release

- **Origin**: Tribunal Superior do Trabalho (TST), Brazil's labor supreme court.
- **Access**: the public frontend (`jurisprudencia.tst.jus.br`) is a React SPA;
  every plausible REST/CKAN/Swagger path tried directly against it 200s with
  the SPA's own `index.html` fallback, not a real endpoint. Its own
  `config.json` (`https://jurisprudencia.tst.jus.br/config.json`) discloses
  the real backend host, `jurisprudencia-backend2.tst.jus.br`, which serves
  `POST /rest/pesquisa-textual/{start}/{size}` - confirmed live 2026-07-07 with
  real paginated JSON records (`totalRegistros`, `registros[].registro`).
- **Confirmed working**: a `tipos` document-type filter (e.g. `["ACORDAO"]`)
  measurably narrows the result count (3.75M of 8.48M total for `ACORDAO`
  alone) and pagination is stable across repeated calls. Record fields include
  `numero`/`numFormatado`, `nomRelator`, `orgaoJudicante`, `dtaJulgamento`,
  `dtaPublicacao`, `ementa`/`ementaHtml`, `txtInteiroTeor` (full ruling text).
- **NOT confirmed / not implemented**: every free-text or exact-lookup filter
  field reverse-engineered from the minified frontend bundle (`ementa`, `e`,
  `ou`, `termoExato`, a `numeracaoUnica` process-number object) was tried live
  and did **not** change the result count, including the exact `numeracaoUnica`
  of a record the endpoint had just returned itself - so only a type-filtered
  browse contract is confirmed, not a "look up this exact case" contract. Per
  this connector's anti-hallucination policy: ship a search tool people can
  trust to actually find a specific case, or don't ship one - this release
  does neither halfway, so no TST tool is exposed. Revisit once an exact-match
  filter is confirmed (e.g. via a browser network trace of the real frontend
  request) or TST publishes open data (dados abertos) analogous to STJ's CKAN
  portal.
- **Querido Diario** (`queridodiario.ok.org.br`) - municipal (not federal) official
  gazettes; out of scope for this connector's federal-legislation/case-law focus.
  Checked live 2026-07-07: the root site and two guessed API paths
  (`/api/v1/gazettes`, `/api/gazettes`) all returned HTTP 403 to a plain client
  (likely a Cloudflare/WAF rule on bare requests, not a hard block - not
  investigated further given the lower priority). Lower priority per task scope.
