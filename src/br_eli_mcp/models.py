"""Pydantic-free plain dataclasses mirroring the Camara dos Deputados JSON shape.

We mirror the upstream field names (camelCase) only where we read them directly
from the JSON payload; everything we hand back to the MCP client is snake_case
and goes through citations.py first.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Proposicao:
    id: int
    sigla_tipo: str
    numero: int
    ano: int
    ementa: str
    data_apresentacao: str | None
    uri: str
    situacao: str | None
    orgao_sigla: str | None


@dataclass(frozen=True)
class Citation:
    lex_uri: str
    human_readable_citation: str
    source_url: str


@dataclass(frozen=True)
class Amendment:
    norma_posterior: str
    data_assinatura: str | None
    comentario: str | None
    dispositivos: tuple[str, ...]


@dataclass(frozen=True)
class Norma:
    """A Norma Juridica resolved from legis.senado.leg.br/dadosabertos/legislacao/urn.

    This is a real ELI-equivalent identification (URN Lex), not a bill in the
    legislative process - contrast with Proposicao above.
    """

    id: str
    tipo: str
    numero: str
    norma_nome: str
    apelido: str | None
    data_assinatura: str | None
    ementa: str
    observacao: str | None
    urn: str
    url_documento: str
    fonte_publicacao: str | None
    amendments: tuple[Amendment, ...]


@dataclass(frozen=True)
class Movimento:
    """One procedural event in a docket's timeline (DataJud ``movimentos``)."""

    codigo: int
    nome: str | None
    data_hora: str | None


@dataclass(frozen=True)
class Processo:
    """A court docket resolved from api-publica.datajud.cnj.jus.br (DataJud CNJ).

    This is procedural docket metadata (parties/classe/timeline), NOT the
    prose text of a ruling - DataJud carries no ementa/acordao full text.
    See caselaw_client.py module docstring for the scope this honestly covers.
    """

    id: str
    tribunal: str
    numero_processo: str
    classe_nome: str | None
    orgao_julgador: str | None
    data_ajuizamento: str | None
    ultima_atualizacao: str | None
    assuntos: tuple[str, ...]
    movimentos: tuple[Movimento, ...]
