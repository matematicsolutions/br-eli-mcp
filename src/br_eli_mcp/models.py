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


@dataclass(frozen=True)
class CasoSTJ:
    """One acordao (ruling) resolved from dadosabertos.web.stj.jus.br (STJ
    Open Data Portal). Carries the real ementa (headnote) and decisao (ruling
    body text) - see stj_client.py module docstring for the coverage window
    (May 2022 onwards only).
    """

    id: str
    orgao_julgador: str
    numero_processo: str
    numero_registro: str | None
    sigla_classe: str | None
    descricao_classe: str | None
    ministro_relator: str | None
    data_decisao: str | None
    data_publicacao: str | None
    ementa: str
    decisao: str | None
    tipo_de_decisao: str | None


@dataclass(frozen=True)
class CasoCARF:
    """One acordao (tax ruling) resolved from acordaos.economia.gov.br (CARF
    Solr open-data index). See carf_client.py module docstring for the exact
    fields confirmed live and the full-text search gap.
    """

    id: str
    numero_processo: str
    numero_decisao: str | None
    camara: str | None
    turma: str | None
    secao: str | None
    relator: str | None
    data_publicacao: str | None
    data_sessao: str | None
    ementa: str | None
    decisao_texto: str | None
    arquivo_pdf: str | None


# NOTE: TST (jurisprudencia-backend2.tst.jus.br) was investigated live in
# v0.5.0 discovery and has a real, confirmed-working backend, but only a
# document-type-filtered browse/pagination contract could be confirmed - no
# exact-match/process-number lookup. Per this fleet's citation contract
# (retrieve a *specific*, verifiable case), a browse-only tool without a
# reliable exact-lookup path is not shipped this release. See DISCOVERY.md
# "TST - real backend CONFIRMED LIVE, but NOT wired into a tool this release".
# CasoTST/parse_caso_tst/build_caso_tst_citation exist for that confirmed
# contract, but no MCP tool calls them yet.
@dataclass(frozen=True)
class CasoTST:
    """One ruling record from the TST jurisprudencia search backend
    (jurisprudencia-backend2.tst.jus.br). See tst_client.py module docstring
    for the confirmed-vs-unconfirmed scope of what can be queried (doc-type
    filter + pagination, NOT free-text or process-number search).
    """

    id: str
    numero_formatado: str | None
    orgao_judicante: str | None
    nome_relator: str | None
    data_julgamento: str | None
    data_publicacao: str | None
    tipo: str | None
    ementa: str | None
    inteiro_teor: str | None
