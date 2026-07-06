"""Citation contract for br-eli-mcp.

Brazil has no live, confirmed SRU/OAI-PMH endpoint for LexML's URN Lex scheme
(the ELI-equivalent identifier) as of 2026-07 - the documented endpoints
returned 404 on live probing. Rather than fabricate a URN Lex, this connector
is honest about what Camara dos Deputados actually gives us: a stable API URI
per proposicao (bill), not a consolidated-law URN. If/when a live LexML
endpoint is confirmed, `lex_uri` should be upgraded to a real urn:lex:br:...
value - see DISCOVERY.md.
"""

from __future__ import annotations

from typing import Any

from .models import Citation, Proposicao

_FICHA_URL = "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={id}"


def parse_proposicao(raw: dict[str, Any]) -> Proposicao:
    status = raw.get("statusProposicao") or {}
    return Proposicao(
        id=raw["id"],
        sigla_tipo=raw["siglaTipo"],
        numero=raw["numero"],
        ano=raw["ano"],
        ementa=raw.get("ementa") or "",
        data_apresentacao=raw.get("dataApresentacao"),
        uri=raw["uri"],
        situacao=status.get("descricaoSituacao"),
        orgao_sigla=status.get("siglaOrgao"),
    )


def build_citation(p: Proposicao) -> Citation:
    human = f"{p.sigla_tipo} {p.numero}/{p.ano}"
    return Citation(
        lex_uri=p.uri,
        human_readable_citation=human,
        source_url=_FICHA_URL.format(id=p.id),
    )
