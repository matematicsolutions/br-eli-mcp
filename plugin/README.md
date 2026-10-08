# br-eli-mcp - Claude plugin

Brazilian federal law with verifiable citations, as a Claude plugin. It runs the
[br-eli-mcp](https://github.com/matematicsolutions/br-eli-mcp) MCP server, version 0.8.3
from PyPI. `uv.lock`, next to the manifest, pins that package and every dependency with
hashes. The plugin starts it with `uvx br-eli-mcp==0.8.3`, and Claude Code's locked launch
installs exactly the set in `uv.lock`, so it runs what was reviewed. (Run by hand outside
Claude Code, plain `uvx` resolves the dependency ranges from PyPI instead.) Every
answer carries the official source and identifier, so a citation can be checked instead
of trusted.

What it covers: bills (Camara dos Deputados), legislation by URN Lex with real article
text (Senado, normas.leg.br), and case law from STJ, TST, TCU and CARF, plus DataJud CNJ
docket metadata. The full tool list and the source notes are in the
[main README](https://github.com/matematicsolutions/br-eli-mcp#readme).

## Requirements

Claude Code or the Claude desktop app, and [uv](https://docs.astral.sh/uv/) on your
machine (its `uvx` installs the locked packages on first start and runs the server).

## Install

```
/plugin marketplace add matematicsolutions/br-eli-mcp
/plugin install br-eli-mcp@br-eli-mcp
```

## Data

The server runs on your machine. Each tool call sends your query to the official
Brazilian public API it names (Camara, Senado, normas.leg.br, DataJud CNJ, STJ, TST,
TCU or CARF) and to nothing else; nothing goes to MateMatic. Your query and the results
also pass through whatever model you use, the same way as any other message.

The standalone server can fetch a small configuration file (updated source addresses) from
this repository's GitHub Releases on first use. The plugin turns that off
(`BR_ELI_RUNTIME_URL` set to empty in `plugin.json`), so it runs only the reviewed code with
its built-in source addresses and makes no request other than the tool calls above.

Two things are written locally, in your home directory:

- a response cache (`~/.matematic/cache/br-eli`), so a repeated lookup does not hit
  the source again. Court rulings are public records and can name the parties.
- an audit log (`~/.matematic/audit/br-eli-mcp.jsonl`), one line per tool call: the
  tool name, a SHA-256 hash of the input (not the input itself), result size, time
  and status.

Delete either folder at any time; `BR_ELI_CACHE_DIR` and `BR_ELI_AUDIT_DIR` move them.

## Licence

Apache-2.0, see the repository's [LICENSE](https://github.com/matematicsolutions/br-eli-mcp/blob/main/LICENSE).
Source data terms are in [SOURCES.md](https://github.com/matematicsolutions/br-eli-mcp/blob/main/SOURCES.md).
