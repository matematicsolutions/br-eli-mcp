# Discovery notes - Brazil

Date: 2026-07-06 (v0.1.0). Updated 2026-07-06 (v0.2.0) - the "not confirmed
live" conclusion below was wrong. It tested the wrong host.

## v0.2.0 update - live endpoint found: legis.senado.leg.br/dadosabertos

The v0.1.0 probe (below) only tried `www.lexml.gov.br`. The actual live
service for Normas Juridicas (URN Lex resolution) is the Congresso Nacional's
own API gateway: `https://legis.senado.leg.br/dadosabertos`, documented via a
public Swagger UI (`/dadosabertos/api-docs/swagger-ui/index.html`) and an
OpenAPI 3.1 spec (`/dadosabertos/v3/api-docs`). The spec states explicitly:
"API de acesso publico, sem necessidade de autenticacao" (public access API,
no authentication needed). This is not an API-key situation like
fr-eli-mcp/PISTE - no key, no registration. Rate limit: 10 req/s (HTTP 429
above that), enforced upstream.

Confirmed live 2026-07-06 with a real query for the Codigo Civil:

```
GET https://legis.senado.leg.br/dadosabertos/legislacao/urn?urn=urn:lex:br:federal:lei:2002-01-10;10406
Accept: application/json
-> HTTP 200, real data: identificacao (apelido "Codigo Civil (2002) (CC)"),
   publicacoes (Diario Oficial da Uniao provenance), vides (amendment
   history per-article). The response's own `observacao` field carries
   free-text notes from the Senado's editors, including references to STF
   rulings on specific articles (e.g. ADI 2.794-8 on Art. 66 par.1) - this is
   the API's data, not a claim we are asserting independently, and it is not
   a substitute for checking the ruling itself.
```

This is now wired into `br_get_norma` (see `norma_client.py` / `citations.py`
/ `server.py`). The URN Lex the caller queries with is echoed back as
`lex_uri` - never invented, per Article IV (parse ELI, don't invent it).

**Remaining gap: full article text is still not a confirmed API.**
`br_get_norma` gives identification, provenance, and amendment history, but
not the compiled article-by-article text (unlike `es_get_text` in
es-eli-mcp). The full compiled text is publicly readable at
`www.planalto.gov.br/ccivil_03/...` (confirmed live 2026-07-06, e.g.
`l10406compilada.htm` for the Codigo Civil, ~900KB HTML with real numbered
articles), but no mechanical rule from a URN Lex to its Planalto URL could be
confirmed - URL paths vary by decade-folder and act type, not law
number+year alone. Scraping Planalto without a confirmed URL-derivation rule
would risk the same fabricated-citation failure mode this fleet exists to
prevent, so do not add a `br_get_text` tool until a URN-Lex-to-Planalto-URL
mapping is confirmed (candidate next step: audit whether
`Mcp-Brasil/mcp-brasil`, MIT, already solved this mapping).

## v0.1.0 original notes (superseded above, kept for the record)

### LexML SRU/OAI-PMH - NOT confirmed live (wrong host tested)

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
