# Discovery notes - Brazil

Date: 2026-07-06.

## LexML SRU/OAI-PMH - NOT confirmed live

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

**Conclusion**: either the service moved, requires a host/port not documented
publicly, or has been discontinued. Do not fabricate a `urn:lex:` identifier
without a confirmed live source - this violates the citation-grounding
principle of the whole eli-mcp fleet (Article IV: parse ELI, don't invent it).

**Revisit**: if a live LexML endpoint is confirmed later (e.g. by a WM
courtesy contact with the project, or discovery of a moved host), add
`br_get_act`/`br_get_text` tools carrying a real `lex_uri` here.

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
