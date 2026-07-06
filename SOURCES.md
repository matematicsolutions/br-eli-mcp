# Sources

## Camara dos Deputados open data (`dadosabertos.camara.leg.br`)

- **Origin**: Camara dos Deputados (Brazilian Chamber of Deputies)
- **License**: open data, attribution required, low legal risk. Verified against
  [Mcp-Brasil/mcp-brasil SOURCES.md](https://github.com/Mcp-Brasil/mcp-brasil/blob/main/SOURCES.md)
  (`Legislativo (Camara, Senado) | Baixo | Open data; atribuicao`).
- **Access**: keyless REST, JSON.
- **Coverage**: this connector only calls `/proposicoes` (list + detail). It does
  not cover Senado, votacoes, deputados, or any other Camara/Senado endpoint.

## Not covered (out of scope for this connector)

- **LexML** (`lexml.gov.br`) - documented `urn:lex:br:...` identifier scheme, but
  no live SRU/OAI-PMH endpoint confirmed reachable as of 2026-07. See DISCOVERY.md.
- **DataJud/CNJ** (case law) - Resolucao CNJ 331/2020 and 446/2022 require your own
  API key and **forbid bulk redistribution**. Any future connector needs a
  bring-your-own-key model (like `fr-eli-mcp`'s PISTE OAuth), not bulk hosting.
- **Planalto** (presidential law texts) - HTML search only, no confirmed API.
