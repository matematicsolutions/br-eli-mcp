# Discovery notes - Brazil

Current as of 2026-07-06 (v0.4.0). History below - earlier releases (v0.1.0,
v0.2.0) each got something wrong; the corrections are kept for the record,
not because they're still live guidance.

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
