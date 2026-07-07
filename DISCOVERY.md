# Discovery notes - Brazil

Current as of 2026-07-07 (v0.6.0). History below - earlier releases (v0.1.0,
v0.2.0, v0.5.0) each got something wrong; the corrections are kept for the
record, not because they're still live guidance.

## v0.6.0 update - TST exact-match confirmed (v0.5.0 rejection reversed) + TCU wired in; TRF4/TRF5 and RFB rejected

Widen round, same day as v0.5.0. All probes 2026-07-07.

**TST - the v0.5.0 "unreliable_exact_match" rejection was wrong, and the fix
is exactly what v0.5.0's own notes prescribed**: a browser network trace of
the real frontend (`jurisprudencia.tst.jus.br`) submitting a search captured
the true request body of `POST jurisprudencia-backend2.tst.jus.br/rest/
pesquisa-textual/{start}/{size}`. Two fields the v0.5.0 static analysis of
the minified bundle missed turn the silently-no-oping filters into working
ones: a top-level `"orgao": "TST"` and `numeracaoUnica.orgao` defaulting to
`"5"`. Replayed from a bare httpx client: baseline ACORDAO 3,751,594
(`totalRegistros`); free text `e='"adicional de insalubridade"'` narrows to
228,802; a fully-populated `numeracaoUnica` for a case the endpoint itself
returned (AIRR 21036-38.2019.5.04.0021) narrows to exactly 1 - the queried
case. Two more gotchas caught live: (a) `DECISAO_MONOCRATICA`, listed in the
frontend's own `config.json` and trusted by v0.5.0, is NOT a valid `tipos`
code - the backend silently ignores it and returns the full 8,483,448-doc
corpus, so `tst_client.DOC_TYPES` whitelists only the eight codes the real
frontend sends, each individually verified to change the total; (b)
`txtInteiroTeor` is often redacted to the literal string "removido no
backend" while the same record carries the full prose in `inteiroTeorHtml`
(59K chars on the sample) - the parser falls back to the HTML field,
mechanically flattened. Wired as `br_search_case_tst` / `br_get_case_tst`.

**TCU - wired in.** The open-data JSON feed
(`dados-abertos.apps.tcu.gov.br/api/acordao/recupera-acordaos`) is live but
its filter params silently no-op (ano/numero/colegiado all returned the same
newest-first page) and records carry only the sumario. The search portal's
own backend, found via the SPA bundle config plus a network trace, is the
real machine interface: `GET pesquisa.apps.tcu.gov.br/rest/publico/base/
acordao-completo/documentosResumidos?termo=...&quantidade=N&inicio=M`
(dedicated total `quantidadeEncontrada`: 525,620 unfiltered, 53,320 for
`licitação`; field-scoped `NUMACORDAO:1771 ANOACORDAO:2026` -> 3, one per
colegiado; adding `COLEGIADO:"Plenário"` -> 1) and `GET .../documento?termo=
KEY:"..."` returning the full ruling prose (`ACORDAO` deliberation,
`RELATORIO` 35K chars, `VOTO` 25K chars on the sample record). Wired as
`br_search_case_tcu` / `br_get_case_tcu`.

**TRF4 / TRF5 - rejected, `geo_restricted` (connection-level).**
`jurisprudencia.trf4.jus.br`, `juliapesquisa.trf5.jus.br` and even
`www.trf5.jus.br` never establish a TCP connection from this (EU) client -
"All connection attempts failed" across two probe rounds minutes apart,
while every other .jus.br host probed the same minute connected fine.
Consistent with country-level network blocking, not an outage. Re-check from
a BR vantage point before believing this rejection forever.

**RFB Solucoes de Consulta (sijut2consulta) - rejected, no machine API.**
`normas.receita.fazenda.gov.br/sijut2consulta/consulta.action` is a
server-rendered Struts HTML app; the search page's own markup references only
`.action` HTML endpoints (no XHR/JSON backend to lift, unlike TST/TCU).
Scrape-class source - off-principle for this keyless-JSON connector line.

**TJDFT / TJBA (state courts) - not probed this round**: the shortlist's
rule was "state courts only if the federal targets fail", and TST + TCU both
shipped. Left as explicit `todo` rows in SOURCES.md, not silent omissions.

## v0.5.0 update - STJ + CARF ruling text wired in; TST backend found but not wired in; Planalto re-checked and still skipped

Starting point: `https://raw.githubusercontent.com/worldwidelaw/legal-sources/main/manifest.yaml`,
entries `BR/Planalto`, `BR/STJDadosAbertos`, `BR/TST`, `BR/CARF`,
`BR/QueridoDiario`. The manifest documents *that* a scraper for each source
exists in that project, not the exact live endpoint shape - every URL and
JSON field below was independently re-confirmed with a live HTTP request
against the actual host, not copied from the manifest's notes.

### STJ Open Data Portal - CONFIRMED LIVE, WIRED IN

`https://dadosabertos.web.stj.jus.br` is a CKAN open-data portal, not a
per-case REST search API. Confirmed live:

- `GET /api/3/action/package_list` -> lists 10 chamber/section datasets, e.g.
  `espelhos-de-acordaos-terceira-secao`, one per `orgao julgador` (Corte
  Especial, 1a/2a Secao, 1a-6a Turma).
- `GET /api/3/action/package_show?id=<dataset>` -> lists that dataset's dated
  resources: one cumulative history ZIP (~9MB, from 2022-05-08) plus ~50
  monthly JSON delta files (one per month since), the newest being
  `20260531.json` at the time of this check.
- Each monthly JSON file is a flat list of acordao ("espelho do acordao")
  records. A live sample record (`20260531.json` from the Terceira Secao
  dataset) had these keys: `id`, `numeroDocumento`, `numeroProcesso`,
  `numeroRegistro`, `siglaClasse`, `descricaoClasse`, `classePadronizada`,
  `nomeOrgaoJulgador`, `ministroRelator`, `dataPublicacao`, `ementa`,
  `tipoDeDecisao`, `dataDecisao`, `decisao`, `jurisprudenciaCitada`, `notas`,
  `informacoesComplementares`, `termosAuxiliares`, `teseJuridica`, `tema`,
  `referenciasLegislativas`, `acordaosSimilares`. Both `ementa` and `decisao`
  carried real multi-paragraph Portuguese prose, not a metadata stub.

**Scope, honestly stated**: the portal's own CKAN dataset notes say "espelhos
data from May 2022 onwards" - there is no public full-text API for
pre-2022 STJ decisions. This is a bulk-snapshot dataset, not a live
search-by-case-number service - `stj_client.py` downloads a bounded number
of the most recent monthly files and filters in-memory, rather than mirroring
the whole corpus, to keep this a lookup tool. Wired in as
`br_search_case_stj` / `br_get_case_stj`.

### CARF - CONFIRMED LIVE, WIRED IN

`https://acordaos.economia.gov.br/solr/acordaos2/select` is a public, keyless
Apache Solr index. Confirmed live:

- `GET ?q=*:*&rows=1&wt=json` -> `numFound: 579226` documents.
- Exact-field query `q=numero_processo_s:"13896.904173/2008-79"` returns
  exactly 1 matching document (confirmed `numFoundExact: true`).
- Live document fields: `id`, `numero_processo_s`, `numero_decisao_s`,
  `camara_s`, `turma_s`, `secao_s`, `nome_relator_s`, `dt_sessao_tdt`,
  `dt_publicacao_tdt`, `dt_registro_atualizacao_tdt`, `ementa_s`,
  `decisao_txt` (list of strings - the ruling body), `conteudo_txt` (OCR/Tika
  full-text dump of the source PDF, including Tika metadata preamble),
  `nome_arquivo_s`, `nome_arquivo_pdf_s`, `arquivo_indexado_s`.
- `conteudo_txt` free-text query (`q=conteudo_txt:"imposto de renda"`)
  returned **zero hits** on a live probe, despite that exact phrase appearing
  in `ementa_s`/`conteudo_txt` of documents known to exist in the index -
  i.e. the full-text index is not reliably populated/analyzed for common
  terms. This matches a caveat already in the manifest's own upstream notes
  for `BR/CARF` ("0 in Neon is VPS pipeline issue"). Rather than guess a
  working full-text query syntax, `carf_client.py` only exposes exact
  `numero_processo_s` / `numero_decisao_s` lookup - no free-text search tool
  for CARF.
- No confirmed live document/PDF URL: probing
  `https://acordaos.economia.gov.br/solr/acordaos2/<nome_arquivo_pdf_s>`
  returned HTTP 404, and the CARF public frontend
  (`https://carf.fazenda.gov.br/` -> redirects to `https://idg.carf.fazenda.gov.br/`)
  did not respond to a plain HTTP client within a generous timeout. `source_url`
  therefore points at the confirmed-live Solr endpoint, never a guessed PDF path.

Wired in as `br_get_case_carf` only (no search tool, per above).

### Planalto (REFLEGIS) - RE-CHECKED, STILL SKIPPED

The manifest's `BR/Planalto` entry names
`https://legislacao.presidencia.gov.br/` (REFLEGIS) and reports its own
scraper as "complete" - but that describes a different project's browser-
automation pipeline, not a documented API. Live re-check 2026-07-07:
`curl -v https://legislacao.presidencia.gov.br/` completes the TCP+TLS
handshake but then times out after 15s with **zero bytes received** on the
HTTP response - consistent with a bot-challenge/WAF gate in front of the
site, not a structured API a keyless HTTP client can use. This confirms and
extends this repo's pre-existing rejection of Planalto (see "Not covered" in
SOURCES.md and the README note): still no confirmed mechanical rule mapping
a URN Lex to a Planalto URL, and now also confirmed that plain HTTP clients
cannot even load the page to attempt one. Not implemented.

### TST - real backend CONFIRMED LIVE, but NOT wired into a tool this release

`https://jurisprudencia.tst.jus.br/` is a React single-page app. Checked
live 2026-07-07:

- The root page returns HTTP 200 with the SPA shell HTML, referencing one
  JS bundle: `/static/js/main.be6b1d66.js`. Every plausible API path tried
  directly against the frontend host (`/api-jurisprudencia-nacional/api/`,
  `/api-jurisprudencia-nacional/api/jurisprudencia/pesquisa`, a CKAN-style
  `package_list` path by analogy with STJ, a POST `/pesquisa`) returned
  either HTTP 200 with `content-type: text/html` (the SPA's own
  client-side-routing fallback) or HTTP 405. The minified JS bundle itself
  had no plain-text API base URL or `REACT_APP_*`-style env var.
- **Follow-up that found the real backend**: the SPA loads its API base URL
  at runtime from `https://jurisprudencia.tst.jus.br/config.json`, which
  discloses `"base_url": "https://jurisprudencia-backend2.tst.jus.br"` (plus
  three unrelated `consultadocumento.tst.jus.br`/`consultaprocessual.tst.jus.br`
  URLs for other TST systems, not probed further). A direct
  `POST https://jurisprudencia-backend2.tst.jus.br/rest/pesquisa-textual/1/2`
  with body `{"tipos": ["ACORDAO"]}` returned real data: `totalRegistros`
  and a `registros` array of real rulings with `numero`/`numFormatado`,
  `nomRelator`, `orgaoJudicante`, `dtaJulgamento`, `dtaPublicacao`,
  `ementa`/`ementaHtml`, `txtInteiroTeor` (full ruling prose).
- **Confirmed working**: the `tipos` filter measurably narrows the count
  (3.75M of 8.48M total documents for `ACORDAO` alone), and pagination via
  the `{start}/{size}` path segments returns stable, disjoint pages across
  repeated calls.
- **NOT confirmed**: filter fields reverse-engineered from the minified
  frontend bundle for free-text/exact search (`ementa`, `e`, `ou`,
  `termoExato`, a `numeracaoUnica` object shaped `{numero, digito, ano,
  orgao, tribunal, vara}` for process-number lookup) were tried live and did
  **not** change the result count in any combination tested - including the
  exact `numeracaoUnica` of a record the endpoint had just returned itself.
  Either the real request shape differs from what the static bundle appears
  to construct, or the endpoint silently ignores filters it does not
  recognize from a bare client (e.g. a session/CSRF header this client does
  not send).

**Decision**: this session built `tst_client.py` implementing only the
confirmed contract - a `tipos`-filtered, paginated browse, plus a
best-effort local scan for a record by its own `id` (not a general lookup,
since there is no dedicated get-by-id endpoint) - plus `CasoTST` /
`parse_caso_tst` / `build_caso_tst_citation` in `models.py`/`citations.py`,
and offline + live tests (`tests/test_tst_parse_offline.py`,
`tests/test_tst_smoke.py`). All of that is **kept in the codebase and
tested**, but deliberately **not wired into a `server.py` MCP tool** this
release: this fleet's citation contract is about trustworthy retrieval of a
specific case, and a browse-only client without a working "find this exact
case" filter does not meet that bar cleanly enough to expose as a tool
without a stronger disclaimer than seems wise for v0.5.0. Revisit once an
exact-match filter is confirmed (e.g. via a browser network trace of the
real frontend request, which may send headers or a request shape this
static-analysis pass could not recover) or TST publishes a documented dados
abertos API analogous to STJ's CKAN portal.

### Querido Diario - checked live, blocked (Cloudflare bot challenge)

`BR/QueridoDiario` (manifest: `https://queridodiario.ok.org.br`) covers
municipal official gazettes, not federal legislation or case law - already
out of this connector's federal-focused scope, and checked live 2026-07-07
for completeness anyway: `GET https://queridodiario.ok.org.br/api/gazettes`
returns HTTP 403 with a Cloudflare "Just a moment..." bot-challenge page
(`cf-mitigated` JS challenge), not JSON - the same failure mode already
recorded elsewhere in this fleet for `pt-PT` sources (see MEMORY note on
dre.tretas.org). Not implemented, both because it is out of scope and
because it is currently blocked to a plain HTTP client.

## v0.4.0 update - DataJud CNJ court dockets (confirmed live, scoped honestly)

Added `br_search_processos` / `br_get_processo` against
`api-publica.datajud.cnj.jus.br` (DataJud CNJ). This closes part of the
"zero case law" gap the fleet had at v0.3.0 - but only part, and the scope
below is deliberately narrow and honest about what it is NOT.

**What was confirmed live** (real HTTP request, not a guess):

```
POST https://api-publica.datajud.cnj.jus.br/api_publica_stj/_search
Authorization: APIKey cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw==
Content-Type: application/json
{"query": {"match_all": {}}, "size": 1}

-> HTTP 200, real STJ docket JSON: numeroProcesso, classe.nome
   ("Agravo em Recurso Especial"), orgaoJulgador, dataAjuizamento, a full
   `movimentos` timeline (Distribuicao, Conclusao, Publicacao, Peticao,
   Provimento em Parte, ...), and `assuntos`.
```

The API key above is CNJ's own openly-published shared key (DataJud Wiki,
https://datajud-wiki.cnj.jus.br/api-publica/acesso/ - "Autenticacao ... por
meio de uma Chave Publica, gerada e disponibilizada pelo DPJ/CNJ"), not
something reverse-engineered or scraped from a leak. CNJ states the key can
be rotated at any time, so the client reads it from `BR_ELI_DATAJUD_KEY` if
set, falling back to the published value in `caselaw_client.py`.

**Endpoints/index aliases** (confirmed via
https://datajud-wiki.cnj.jus.br/api-publica/endpoints/): one index per
tribunal, `api_publica_<code>` - `stj`, `tst`, `tse`, `stm`, `trf1..trf6`,
`tj<uf>` (27 state courts), `trt1..trt24`, `tre-<uf>` (27 electoral courts),
plus 3 military courts. All wired into `TRIBUNAL_INDEX` in `caselaw_client.py`.

**What this genuinely is NOT** (confirmed by testing, not assumed):

- **Not full-text jurisprudencia search.** DataJud indexes procedural
  *docket* metadata sourced from each court's case-management system via the
  Modelo Nacional de Interoperabilidade - `numeroProcesso`, `classe`,
  `orgaoJulgador`, `assuntos`, and `movimentos` (a timeline of procedural
  events, e.g. "Distribuicao", "Publicacao", "Provimento em Parte"). It does
  **not** carry the prose text of a ruling/acordao/ementa. A `movimento`
  entry is an event label, not a holding - `br_get_processo`'s docstring and
  the server `INSTRUCTIONS` say this explicitly so the calling LLM doesn't
  present a movement as if it quoted a court's reasoning.
- **STF is not covered - confirmed by a live 404, not an assumption:**

  ```
  POST https://api-publica.datajud.cnj.jus.br/api_publica_stf/_search
  -> HTTP 404 {"error":{"type":"index_not_found_exception",
                "reason":"no such index [api_publica_stf]", ...}}
  ```

  This is structural, not an outage: the STF sits outside the CNJ's
  regulatory reach in a way STJ/TST/TRFs/TJs/etc. do not, so it never feeds
  DataJud via the interoperability model the other 91 courts use. There is
  no `br_get_stf_decisao` tool in this release because there is no confirmed
  live source for it (see "still open" below).

**Redistribution constraint carried forward from the v0.3.0 audit**
(Resolucao CNJ 446/2022: bulk redistribution is restricted; docket data can
carry LGPD-sensitive party information): `caselaw_client.py` only performs
live, on-demand queries against the shared key - it caches individual query
results with a short TTL like the other "search"/"act" categories, and never
bulk-downloads or persists a corpus. This is the "bring-your-own-shared-key,
live-query-only" model the v0.3.0 note already called for.

### Still open: no full-text STF/STJ ruling-text source found

Two other leads from this session's research were tried and did not pan out
as a full-text jurisprudencia source:

- A guessed HuggingFace dataset name (`eduagarcia/BrazilianCourtDecisionsHF`)
  returned 401 in earlier probing this session; no genuinely public,
  ungated, confirmed-real HuggingFace Brazilian-court-decisions dataset was
  found to replace it as a fallback in the time available. If one exists it
  was not surfaced by search in this session - this is a documented gap, not
  a claim that none exists.
- STF's own portal and LexML/BR were already flagged unreliable by the wider
  `worldwidelaw/legal-sources` audit (AWS WAF block on STF, 404s on LexML/BR)
  before this session started - not retried blindly here, consistent with
  that audit's own findings.

**Conclusion**: full ruling-text jurisprudencia (STF sumulas/acordaos, STJ
acordao text) remains an open gap for a future session. What v0.4.0 adds is
real and useful on its own terms - docket status/timeline/classe/assuntos
lookup across 91 non-STF courts - but callers should not expect it to answer
"what did the court hold" questions; only "what happened procedurally, and
when."

**Operational note added in this session's test run (2026-07-06): DataJud's
public API is genuinely slow and occasionally flaky.** Five repeated,
byte-identical `curl` requests for `{"query":{"match":{"classe.nome":"Agravo"}},
"size":1}` against `api_publica_stj` returned: one `HTTP 429` (rate limit),
then four `HTTP 200`s with response times ranging 11.8s-38.8s. Separately, the
same query against a field with 10000+ matching documents returned `hits.hits`
as an empty list on one attempt and populated on the next (`hits.total` stayed
`{"value": 10000, "relation": "gte"}` throughout - it's the returned `hits`
array, not the total count, that is unreliable under load). This produced one
flaky failure in `tests/test_caselaw_smoke.py::test_get_processo_by_numero`
during this session's pytest run (`5 passed, 1 failed` on one run; a rerun of
just that file passed 2/3, failed a different one) - confirmed via direct
`curl` to be DataJud's own instability, not a bug in `caselaw_client.py`'s
retry/cache logic. The client's existing `_RETRY_STATUS` set already retries
429/5xx; a future session could consider also retrying on HTTP 200 responses
with an unexpectedly empty `hits.hits` for a query whose `hits.total` is
nonzero, if this proves persistent.

## Current status (legislation APIs, v0.2.0/v0.3.0)

Two APIs, both public, keyless, no registration:

- `legis.senado.leg.br/dadosabertos` resolves a URN Lex to identification,
  Diario Oficial da Uniao publication provenance, and amendment history
  (`br_get_norma`). Confirmed live with a real query for the Codigo Civil:

  ```
  GET https://legis.senado.leg.br/dadosabertos/legislacao/urn?urn=urn:lex:br:federal:lei:2002-01-10;10406
  Accept: application/json
  -> HTTP 200, real data: identificacao (apelido "Codigo Civil (2002) (CC)"),
     publicacoes (DOU provenance), vides (amendment history per-article).
     The `observacao` field carries the Senado's own editorial notes,
     including references to STF rulings on specific articles (e.g. ADI
     2.794-8 on Art. 66 par.1) - that's the API's data, not our claim, and
     it isn't a substitute for checking the ruling itself.
  ```

  Wired into `br_get_norma` (`norma_client.py` / `citations.py` /
  `server.py`). The URN Lex the caller queries with is echoed back as
  `lex_uri` - never invented, per Article IV (parse ELI, don't invent it).

- `normas.leg.br/api/public/normas` resolves the same URN Lex to a schema.org
  `Legislation` JSON-LD tree - one node per Parte/Livro/Titulo/Capitulo/Secao/
  Artigo/paragrafo, each with its own URN Lex suffix and, on leaf nodes, real
  inline article text (`br_get_norma_index` + `br_get_norma_texto`). This is
  a different path on the same domain as the human-readable citation page -
  the v0.2.0 session only checked the frontend, not its backing API. Tested
  against the Codigo Civil (`urn:lex:br:federal:lei:2002-01-10;10406`): 2511
  addressable nodes, `art1`'s text matches Art. 1 of the Codigo Civil. Full
  response saved as `tests/fixtures/codigo_civil_normas.json` (5.3MB -
  public-domain Brazilian federal legislation, no licensing concern in
  redistributing it as a test fixture). Wired into `text_client.py` /
  `norma_text.py`, both written clean-room against the live response - no
  code reused from any AGPL project (see the `worldwidelaw/legal-sources`
  note below).

- This connector does not scrape Planalto (planalto.gov.br) HTML. No
  confirmed mechanical rule maps a URN Lex to a Planalto URL for every act
  type, and fabricating one would risk the same citation-hallucination
  failure mode this fleet exists to prevent. A minority of act types (mostly
  decrees, `DEC-n`/`MPV-ss`) have no inline text on `normas.leg.br` either -
  a Planalto-scraping fallback for those is a candidate follow-up, to be
  written clean-room if picked up.

### Note on `worldwidelaw/legal-sources` (AGPL-3.0)

That project's `sources/BR/Planalto/bootstrap.py` solves a different problem:
a URL-derivation rule for scraping Planalto HTML, used as its own fallback
when `normas.leg.br` has no inline text. Reading it for method - per the
fleet's own recon step 0 in `PLAYBOOK.md` - is what pointed this session at
probing `normas.leg.br` directly. No code, regex, or URL template from that
AGPL codebase was copied into this Apache-2.0 one.

## History

### v0.2.0 - fixed identification, still missing full text

v0.1.0 (below) had tested the wrong host for identification. v0.2.0 fixed
that by finding `legis.senado.leg.br/dadosabertos` - see "Current status"
above - but at the time concluded there was no confirmed way to get full
article text, and specifically ruled out scraping Planalto without a
confirmed URL rule. That gap is closed above by `normas.leg.br`'s JSON-LD
tree, which needs no such rule.

### v0.1.0 - LexML SRU/OAI-PMH not confirmed live (wrong host tested)

LexML documents an SRU (Search/Retrieval via URL) service and a `urn:lex:br:...`
identifier scheme (Brazil's ELI-equivalent, same lineage as the Italian URN-NIR).
Live probing on 2026-07-06 returned HTTP 404 on every candidate path tried
against `www.lexml.gov.br` (`/busca/SRU`, `/sru`, `/SRU`, `/busca/sru`,
`/api/sru`, `/busca/oaisearch`, `/oai/oai.php`). The official technical PDF
(`projeto.lexml.gov.br/documentacao/Parte-4-Coleta-de-Metadados.pdf`) documents
the metadata schema but not a live base URL. A third-party wrapper
(`netoferraz/py-lexml-acervo`, GPL-3.0, last active ~2019) references the same
SRU standard without a working example URL in its README at the time of
checking.

**Conclusion (SUPERSEDED)**: was "either the service moved... or discontinued".
Correction: it moved to `legis.senado.leg.br/dadosabertos` - see the v0.2.0
update above.

## DataJud/CNJ - confirmed live, redistribution-restricted (WIRED IN v0.4.0)

`api-publica.datajud.cnj.jus.br` is a real, unified Elasticsearch-backed REST
API across 91 courts (state + federal + labor + electoral), ~80M+ active
cases (per Mcp-Brasil audit, CNJ Justica em Numeros). Access uses a single
publicly-documented shared API key (not per-developer registration in the
usual sense) - but **Resolucao CNJ 446/2022 forbids bulk redistribution**, and
case data involving family/juvenile/criminal matters is LGPD-sensitive
(comparable to RODO special categories). This session's follow-up (see
"v0.4.0 update" above) confirmed the exact key, endpoint list, and query DSL
with a real HTTP request, and wired it in as `br_search_processos` /
`br_get_processo` - live bring-your-own-shared-key queries only, never
bulk-hosted, per the constraint already identified here.

## Camara dos Deputados - confirmed live, low risk

`dadosabertos.camara.leg.br/api/v2/proposicoes` - keyless JSON, works as
documented. This is what `br-eli-mcp` v0.1.0 actually implements.
