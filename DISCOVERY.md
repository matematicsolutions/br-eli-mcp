# Discovery notes - Brazil

Current as of 2026-07-06 (v0.3.0). History below - three earlier releases
(v0.1.0, v0.2.0) each got something wrong; the corrections are kept for the
record, not because they're still live guidance.

## Current status

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

## DataJud/CNJ - confirmed live, but redistribution-restricted

`api-publica.datajud.cnj.jus.br` is a real, unified Elasticsearch-backed REST
API across 91 courts (state + federal + labor + electoral), ~80M+ active
cases (per Mcp-Brasil audit, CNJ Justica em Numeros). Access uses a single
publicly-documented shared API key (not per-developer registration in the
usual sense) - but **Resolucao CNJ 446/2022 forbids bulk redistribution**, and
case data involving family/juvenile/criminal matters is LGPD-sensitive
(comparable to RODO special categories). Any future connector for this must
be a live bring-your-own-key model, never bulk-hosted like the EU legislation
connectors in this fleet.

## Camara dos Deputados - confirmed live, low risk

`dadosabertos.camara.leg.br/api/v2/proposicoes` - keyless JSON, works as
documented. This is what `br-eli-mcp` v0.1.0 actually implements.
