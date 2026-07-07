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
## TST (`jurisprudencia-backend2.tst.jus.br`) - WIRED IN v0.6.0 (v0.5.0 rejection reversed)

- **Origin**: Tribunal Superior do Trabalho (TST), Brazil's labor supreme court.
- **Access**: the public frontend (`jurisprudencia.tst.jus.br`) is a React SPA;
  its own `config.json` discloses the real backend host,
  `jurisprudencia-backend2.tst.jus.br`, which serves
  `POST /rest/pesquisa-textual/{start}/{size}` - keyless JSON, confirmed live
  2026-07-07 (`totalRegistros`, `registros[].registro`).
- **v0.5.0 rejected this as `unreliable_exact_match`** because every filter
  field reverse-engineered from the minified bundle silently no-oped. That
  rejection is REVERSED in v0.6.0: a browser network trace of the real
  frontend (the exact re-check v0.5.0's own notes prescribed) showed the true
  request body carries a top-level `"orgao": "TST"` and a `numeracaoUnica`
  whose `orgao` sub-field defaults to `"5"` - with those two fields present,
  the same filters work from a bare HTTP client. Confirmed live 2026-07-07:
  baseline `tipos=["ACORDAO"]` = 3,751,594; free text `e` narrows to 228,802
  for one phrase; a fully-populated `numeracaoUnica` narrows to exactly 1 -
  the queried case. All eight documents types together = 8,483,448.
- **Coverage**: real ruling full text. `txtInteiroTeor` is often redacted
  upstream to the literal "removido no backend", but the same record carries
  `inteiroTeorHtml` (confirmed live, 59K chars on the sample) - the parser
  falls back to that, mechanically flattened to text. Gotcha:
  `DECISAO_MONOCRATICA` (listed in the frontend's own config.json) is NOT a
  valid `tipos` code - the backend silently ignores unknown codes and returns
  the full corpus, so only the eight codes captured from the real frontend
  (each verified to change the total) are accepted.

## TCU (`pesquisa.apps.tcu.gov.br/rest/publico`) - WIRED IN v0.6.0

- **Origin**: Tribunal de Contas da Uniao (TCU), Brazil's Federal Court of
  Accounts - public-procurement and public-spending jurisprudence.
- **License**: public open data (TCU also publishes the same bases as bulk
  CSVs on `sites.tcu.gov.br/dados-abertos/jurisprudencia/`).
- **Access**: keyless REST JSON, confirmed live 2026-07-07.
  `GET /rest/publico/base/acordao-completo/documentosResumidos?termo=...`
  (search; dedicated total field `quantidadeEncontrada` = 525,620 unfiltered)
  and `GET .../documento?termo=...` (full document). The separate open-data
  feed `dados-abertos.apps.tcu.gov.br/api/acordao/recupera-acordaos` was
  probed first and NOT used: live, but its filter params silently no-op and
  its records carry only the sumario.
- **Coverage**: real ruling prose - `ACORDAO` (deliberation), `RELATORIO`
  (rapporteur's report) and `VOTO` (vote), confirmed live (35K+ chars of
  RELATORIO on the sample record). Exact lookup is (numero, ano, colegiado):
  a numero/ano pair alone matches up to one acordao per deciding body
  (confirmed live: `NUMACORDAO:1771 ANOACORDAO:2026` -> 3), so the get tool
  refuses to guess and lists the bodies instead.

## TRF4 / TRF5 (regional federal courts) - rejected v0.6.0, `geo_restricted`

- `jurisprudencia.trf4.jus.br`, `juliapesquisa.trf5.jus.br` and even the TRF5
  main site never establish a TCP connection from this (EU) client - "All
  connection attempts failed" across two probe rounds on 2026-07-07, while
  every other `.jus.br` host probed the same minute connected fine.
  Consistent with country-level network blocking. Re-check from a Brazilian
  vantage point before treating this rejection as permanent.

## RFB Solucoes de Consulta (`normas.receita.fazenda.gov.br/sijut2consulta`) - rejected v0.6.0, no machine API

- Server-rendered Struts HTML application (`consulta.action` /
  `link.action?idAto=...`); the search page's own markup references no
  XHR/JSON backend to lift (unlike TST/TCU, whose SPAs disclosed real JSON
  services). Scrape-class - off-principle for this keyless-JSON connector.
- **Querido Diario** (`queridodiario.ok.org.br`) - municipal (not federal) official
  gazettes; out of scope for this connector's federal-legislation/case-law focus.
  Checked live 2026-07-07: the root site and two guessed API paths
  (`/api/v1/gazettes`, `/api/gazettes`) all returned HTTP 403 to a plain client
  (likely a Cloudflare/WAF rule on bare requests, not a hard block - not
  investigated further given the lower priority). Lower priority per task scope.

## LDH cross-reference ledger (`eu-legal-mcp/PLAYBOOK.md` section 8 convention)

| LDH id | Our status | LDH status @ check | Notes |
|---|---|---|---|
| BR/CamaraDeputados | shipped | - (not recorded at that check) | see above |
| BR/LexML, BR/SenadoLegislacao | shipped | - (not recorded at that check) | see above |
| BR/STJDadosAbertos | shipped | - (not recorded at that check) | see above, 2026-07-07 |
| BR/CARF | shipped | - (not recorded at that check) | see above, 2026-07-07 |
| BR/TST | **shipped v0.6.0** (v0.5.0 rejection `unreliable_exact_match` REVERSED same day) | complete @ 2026-07-07 | exact-match confirmed via browser network trace; see above |
| BR/TCU | shipped v0.6.0 | complete @ 2026-07-07 | 525,620 acordaos, full ruling prose; see above |
| BR/TRF4 | rejected - `geo_restricted` | complete @ 2026-07-07 | no TCP connection from EU client, 2 rounds; see above |
| BR/TRF5 | rejected - `geo_restricted` | complete @ 2026-07-07 | same as TRF4; TRF1/2/6 not probed (different backends, same expected block - verify from BR first) |
| BR/RFB (sijut2consulta) | rejected - `no_machine_api` (scrape-class Struts HTML) | complete @ 2026-07-07 | see above |
| BR/TJDFT | todo | complete @ 2026-07-07 | not probed - shortlist rule was "state courts only if federal targets fail"; TST+TCU shipped |
| BR/TJBA | todo | complete @ 2026-07-07 | same as TJDFT (GraphQL backend per LDH) |
| BR/Planalto | rejected - `bot_protection` | - (not recorded at that check) | see above |
| BR/QueridoDiario | rejected - `bot_protection` | - (not recorded at that check) | see above |
| BR/STF | rejected - `bot_protection` (`aws_waf_browser_required`) | - (not recorded at that check) | blocked for LDH too |

Last updated: 2026-07-07 (v0.6.0 widen round - TST+TCU shipped; see `eu-legal-mcp/AUDIT-LOG.md`).
