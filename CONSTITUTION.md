# Constitution of br-eli-mcp

Version: 0.3.0
Date: 2026-07-06
Licence: Apache-2.0

`br-eli-mcp` is an MCP server for Brazilian federal legislative data provided by the Camara dos
Deputados and the Congresso Nacional (Senado Federal). It searches and retrieves legislative-process
bills, enacted Normas Juridicas, and real article-level text with verifiable URN Lex /
stable-API-URI citations.

The 4 principles below bind every contribution to the project and every tool exposed by this MCP
server. They are inherited from the `eu-legal-mcp` line Constitution (Article IV) - a connector may
tighten them, never weaken them.

---

## Art. 1. Public data only

`dadosabertos.camara.leg.br`, `legis.senado.leg.br/dadosabertos`, and `normas.leg.br/api/public` are
the official, public sources of Brazilian federal legislative data provided by the Camara dos
Deputados and the Congresso Nacional. Legal status of the data: open data, keyless, no
registration - see DISCOVERY.md.

This server must not:
- transfer law-firm client personal data or pleadings to either API (both are read-only for the
  source's data - we send nothing beyond search parameters).
- proxy access to other sources or private databases through this API.

## Art. 2. Mandatory audit log

Every call to every MCP tool MUST be written to `~/.matematic/audit/br-eli-mcp.jsonl` as one JSON
line:

```json
{"ts": "...", "tool": "...", "input_hash": "...", "output_count_or_size": N, "duration_ms": N, "status": "ok|error"}
```

Purpose: operator accountability. `input_hash` is a SHA-256 of the normalized argument form (without
storing raw queries that could contain fragments of client pleadings). Inability to write to the audit
log = inability to run the tool (the tool returns an error, it does not silently skip). The link to AI
Act art. 12 belongs to the deploying entity - the MCP server itself is not a high-risk AI system.

## Art. 3. Vendor neutrality

No tool may: hardcode an LLM provider; assume a specific model in prompt engineering; introduce
telemetry to commercial services. The server communicates only with `dadosabertos.camara.leg.br`,
`legis.senado.leg.br/dadosabertos`, `normas.leg.br/api/public`, and the local filesystem (cache +
audit). No authentication - all three upstream APIs are public and keyless.

## Art. 4. URN Lex / stable-API-URI citations and a human-readable citation are mandatory

Every response from every tool MUST contain three fields:
- `lex_uri`: the canonical identifier - a real `urn:lex:br:federal:...` (from `br_get_norma`, echoed
  back verbatim, never invented - e.g. `urn:lex:br:federal:lei:2002-01-10;10406`), that same URN plus
  an article suffix from `br_get_norma_index` (from `br_get_norma_texto`, e.g.
  `urn:lex:br:federal:lei:2002-01-10;10406!art5`), or, for bills that are not yet enacted law, the
  Camara's own stable API URI (from `br_search_proposicoes` / `br_get_proposicao`).
- `human_readable_citation`: a citation in Brazilian legal convention (e.g. `"PL 2597/2024"` for a
  bill, `"Codigo Civil (2002) (CC)"` for an enacted norma, `"Art. 5o"` for one article).
- `source_url`: a full URL by which this document can be retrieved independently of the MCP
  (`camara.leg.br` tramitacao page or `normas.leg.br`).

Purpose: verifiability. An LLM never presents content without the ability to click the link and check
the original. The presence of these fields is a necessary, not a sufficient, condition with respect
to rules on the admissibility of evidence.

---

## Constitution evolution

Changes to art. 1-4 require: a SEMVER version bump (PATCH/MINOR/MAJOR), an entry in `CHANGELOG.md`,
and a package version bump in `pyproject.toml`.

First version: 2026-07-06. Author: Wieslaw Mazur / MateMatic.
