"""Citation contract for br-eli-mcp.

Two independent sources are wired here:

1. Camara dos Deputados (proposicoes) - the legislative *process*. A bill has
   no URN Lex of its own (it isn't enacted law yet), so `lex_uri` is honestly
   the stable Camara API URI, not a fabricated urn:lex:br:....
2. legis.senado.leg.br/dadosabertos (Normas Juridicas) - CONFIRMED LIVE
   2026-07-06 (see DISCOVERY.md "v0.2.0 update"). This is the real ELI-
   equivalent resolver for enacted law: it returns the actual URN Lex the
   caller queried with (echoed back, not invented - Article IV: parse, don't
   invent), plus DOU publication provenance and amendment history.
"""

from __future__ import annotations

from typing import Any

from .models import Amendment, Citation, Movimento, Norma, Processo, Proposicao

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


def _first_publicacao_fonte(raw: dict[str, Any]) -> str | None:
    pubs = (raw.get("publicacoes") or {}).get("publicacao") or []
    if isinstance(pubs, dict):
        pubs = [pubs]
    return pubs[0].get("fonte") if pubs else None


def _parse_amendments(raw: dict[str, Any]) -> tuple[Amendment, ...]:
    vides = (raw.get("vides") or {}).get("vide") or []
    if isinstance(vides, dict):
        vides = [vides]
    out: list[Amendment] = []
    for v in vides:
        itens = (v.get("itens") or {})
        item_list = itens.get("item") if isinstance(itens, dict) else []
        if isinstance(item_list, dict):
            item_list = [item_list]
        dispositivos = tuple(
            (it.get("dispositivo") or "").strip()
            for it in (item_list or [])
            if it.get("dispositivo")
        )
        out.append(
            Amendment(
                norma_posterior=v.get("nomeNormaPosterior") or v.get("codnormaposterior") or "",
                data_assinatura=v.get("datAssinatura"),
                comentario=v.get("comentario"),
                dispositivos=dispositivos,
            )
        )
    return tuple(out)


def parse_norma(raw: dict[str, Any], urn: str) -> Norma:
    """Parse one `documento` from legis.senado.leg.br/dadosabertos/legislacao/urn.

    `urn` is echoed back verbatim as `Norma.urn` - it is the caller's own query
    input, already a real URN Lex per the LexML scheme (never invented here).
    """
    ident = raw.get("identificacao") or {}
    return Norma(
        id=str(raw.get("id", "")),
        tipo=ident.get("tipo", ""),
        numero=ident.get("numero", ""),
        norma_nome=ident.get("normaNome", ""),
        apelido=ident.get("apelido"),
        data_assinatura=ident.get("dataassinatura"),
        ementa=raw.get("ementa") or "",
        observacao=raw.get("observacao"),
        urn=urn,
        url_documento=ident.get("urlDocumento", f"https://normas.leg.br/?urn={urn}"),
        fonte_publicacao=_first_publicacao_fonte(raw),
        amendments=_parse_amendments(raw),
    )


def build_norma_citation(n: Norma) -> Citation:
    human = n.apelido or n.norma_nome
    return Citation(
        lex_uri=n.urn,
        human_readable_citation=human,
        source_url=n.url_documento,
    )


def _parse_movimentos(raw: dict[str, Any]) -> tuple[Movimento, ...]:
    movs = raw.get("movimentos") or []
    return tuple(
        Movimento(
            codigo=m.get("codigo", 0),
            nome=m.get("nome"),
            data_hora=m.get("dataHora"),
        )
        for m in movs
    )


def parse_processo(raw: dict[str, Any], tribunal: str) -> Processo:
    """Parse one docket ``_source`` from a DataJud CNJ tribunal index.

    `tribunal` is the caller's own query input (a key of
    ``caselaw_client.TRIBUNAL_INDEX``), echoed back - never invented here.
    """
    classe = raw.get("classe") or {}
    orgao = raw.get("orgaoJulgador") or {}
    assuntos_raw = raw.get("assuntos") or []
    return Processo(
        id=str(raw.get("id", "")),
        tribunal=raw.get("tribunal") or tribunal,
        numero_processo=raw.get("numeroProcesso", ""),
        classe_nome=classe.get("nome"),
        orgao_julgador=orgao.get("nome"),
        data_ajuizamento=raw.get("dataAjuizamento"),
        ultima_atualizacao=raw.get("dataHoraUltimaAtualizacao"),
        assuntos=tuple(a.get("nome", "") for a in assuntos_raw if a.get("nome")),
        movimentos=_parse_movimentos(raw),
    )


def build_processo_citation(p: Processo) -> Citation:
    """DataJud carries no per-process public web URL - the CNJ unified process
    number is itself the citable identifier (queryable back into the same
    tribunal index), so `lex_uri`/`source_url` both point at that, honestly -
    not a fabricated URL to a court's own consultation portal we haven't
    verified per-tribunal.
    """
    human = f"{p.tribunal} - Processo {p.numero_processo}"
    return Citation(
        lex_uri=f"datajud:{p.tribunal}:{p.numero_processo}",
        human_readable_citation=human,
        source_url=(
            f"https://api-publica.datajud.cnj.jus.br/api_publica_"
            f"{p.tribunal.lower()}/_search"
        ),
    )
