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

import html
import re
from typing import Any

from .models import (
    Amendment,
    CasoCARF,
    CasoSTJ,
    CasoTCU,
    CasoTST,
    Citation,
    Movimento,
    Norma,
    Processo,
    Proposicao,
)

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
        itens = v.get("itens") or {}
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
            f"https://api-publica.datajud.cnj.jus.br/api_publica_{p.tribunal.lower()}/_search"
        ),
    )


# ---------------------------------------------------------------------------
# STJ (dadosabertos.web.stj.jus.br)
# ---------------------------------------------------------------------------


def parse_caso_stj(raw: dict[str, Any], orgao: str) -> CasoSTJ:
    """Parse one acordao record from a STJ Open Data monthly "espelho" file.

    `orgao` is the caller's own query input (a key of `stj_client.ORGAO_DATASET`),
    echoed back - never invented here.
    """
    return CasoSTJ(
        id=str(raw.get("id", "")),
        orgao_julgador=raw.get("nomeOrgaoJulgador") or orgao,
        numero_processo=raw.get("numeroProcesso", ""),
        numero_registro=raw.get("numeroRegistro"),
        sigla_classe=raw.get("siglaClasse"),
        descricao_classe=raw.get("descricaoClasse"),
        ministro_relator=raw.get("ministroRelator"),
        data_decisao=raw.get("dataDecisao"),
        data_publicacao=raw.get("dataPublicacao"),
        ementa=raw.get("ementa") or "",
        decisao=raw.get("decisao"),
        tipo_de_decisao=raw.get("tipoDeDecisao"),
    )


def build_caso_stj_citation(c: CasoSTJ) -> Citation:
    """STJ's open-data portal carries no per-case public web URL - the
    (numeroProcesso, id) pair is the citable identifier into this same
    dataset, so `lex_uri` reflects that honestly rather than guessing a
    jurisprudencia.stj.jus.br consultation URL we have not confirmed live.
    """
    relator = f", Rel. Min. {c.ministro_relator}" if c.ministro_relator else ""
    data = c.data_decisao or ""
    if len(data) == 8 and data.isdigit():
        data = f"{data[6:8]}/{data[4:6]}/{data[0:4]}"
    julgado_em = f", j. {data}" if data else ""
    human = f"STJ, {c.sigla_classe or 'Processo'} {c.numero_processo}{relator}{julgado_em}"
    return Citation(
        lex_uri=f"stj:{c.orgao_julgador}:{c.numero_processo}",
        human_readable_citation=human,
        source_url="https://dadosabertos.web.stj.jus.br/dataset/",
    )


# ---------------------------------------------------------------------------
# CARF (acordaos.economia.gov.br)
# ---------------------------------------------------------------------------


def parse_caso_carf(raw: dict[str, Any]) -> CasoCARF:
    """Parse one acordao document from the CARF Solr open-data index."""
    decisao_txt = raw.get("decisao_txt")
    if isinstance(decisao_txt, list):
        decisao_txt = "\n".join(decisao_txt)
    return CasoCARF(
        id=str(raw.get("id", "") or raw.get("conteudo_id_s", "")),
        numero_processo=raw.get("numero_processo_s", ""),
        numero_decisao=raw.get("numero_decisao_s"),
        camara=raw.get("camara_s"),
        turma=raw.get("turma_s"),
        secao=raw.get("secao_s"),
        relator=raw.get("nome_relator_s"),
        data_publicacao=raw.get("dt_publicacao_tdt"),
        data_sessao=raw.get("dt_sessao_tdt"),
        ementa=raw.get("ementa_s"),
        decisao_texto=decisao_txt,
        arquivo_pdf=raw.get("nome_arquivo_pdf_s"),
    )


def _carf_pdf_url(c: CasoCARF) -> str | None:
    """Return the CARF acordao PDF URL, confirmed live 2026-07-07.

    Every CARF Solr record already carries its own exact PDF filename in
    `nome_arquivo_pdf_s` (parsed into `c.arquivo_pdf`, e.g.
    ``"16095000602200770_5643663.pdf"``) - that field is the upstream API's
    own data, not something this client derives. The one thing confirmed by
    live probing here is the base path it resolves under
    (`/solr/acordaos2/browse/` renders these filenames as links to
    ``https://acordaos.economia.gov.br/acordaos2/pdfs/processados/<filename>``,
    and fetching that constructed URL for a real record returned HTTP 200
    with a real PDF body, not a 404). So this only ever joins a base path to
    a filename the API already gave us - it never invents the filename
    itself (`numero_processo_s` and the Solr `id` field are NOT the same
    number as the `conteudo_id_s` baked into this filename, so guessing it
    from other fields would be wrong).
    """
    if not c.arquivo_pdf:
        return None
    return f"https://acordaos.economia.gov.br/acordaos2/pdfs/processados/{c.arquivo_pdf}"


def build_caso_carf_citation(c: CasoCARF) -> Citation:
    """`lex_uri` is the confirmed-live PDF URL when derivable (see
    `_carf_pdf_url`); otherwise it falls back to the Solr search endpoint so
    the caller always gets a working `source_url`, never a guessed link.
    """
    relator = f", Rel. {c.relator}" if c.relator else ""
    orgao = c.turma or c.camara or c.secao or "CARF"
    human = f"CARF, {orgao}, Ac. {c.numero_decisao or c.numero_processo}{relator}".rstrip()
    pdf_url = _carf_pdf_url(c)
    return Citation(
        lex_uri=pdf_url or f"carf:{c.numero_processo}",
        human_readable_citation=human,
        source_url=pdf_url or "https://acordaos.economia.gov.br/solr/acordaos2/select",
    )


# ---------------------------------------------------------------------------
# TST (jurisprudencia-backend2.tst.jus.br)
# ---------------------------------------------------------------------------


def parse_caso_tst(raw: dict[str, Any]) -> CasoTST:
    """Parse one ruling record from the TST jurisprudencia search backend.

    `orgaoJudicante` and `tipo` are nested objects in the raw response
    (``{"descricao": ...}`` / ``{"codigoTipoJurisprudencia": ...}``) - this
    reads their sub-fields, it does not invent flattened names. The plain
    ruling-text field (`txtInteiroTeor`) is frequently redacted in this
    endpoint's responses (confirmed live 2026-07-07 - the backend returns
    the literal string ``"removido no backend"``), while the SAME record
    carries the full prose in ``inteiroTeorHtml`` (confirmed live: 59K chars
    of HTML on a record whose plain field was redacted). When that happens,
    `inteiro_teor` falls back to ``inteiroTeorHtml`` mechanically flattened
    to text (`_strip_html` - the upstream's own words, tags removed) - never
    backfilled from anywhere else, never guessed.
    """
    orgao = raw.get("orgaoJudicante") or {}
    tipo = raw.get("tipo") or {}
    inteiro_teor = raw.get("txtInteiroTeor")
    if inteiro_teor == "removido no backend" or not inteiro_teor:
        inteiro_teor = _strip_html(raw.get("inteiroTeorHtml"))
    return CasoTST(
        id=str(raw.get("id", "")),
        numero_formatado=raw.get("numFormatado"),
        orgao_judicante=orgao.get("descricao"),
        nome_relator=raw.get("nomRelator"),
        data_julgamento=raw.get("dtaJulgamento"),
        data_publicacao=raw.get("dtaPublicacao"),
        tipo=tipo.get("nome") or tipo.get("codigoTipoJurisprudencia"),
        ementa=raw.get("ementa"),
        inteiro_teor=inteiro_teor,
    )


def build_caso_tst_citation(c: CasoTST) -> Citation:
    """TST's jurisprudencia backend carries no per-case public web URL -
    `lex_uri` is the opaque `id` this same backend returned, honestly, not a
    guessed consultation URL. `source_url` points at the human-facing search
    frontend (confirmed live), where the `numero_formatado` re-finds the
    case via the process-number filter (the same `numeracaoUnica` contract
    this connector's `br_get_case_tst` uses, confirmed live 2026-07-07).
    """
    relator = f", Rel. {c.nome_relator}" if c.nome_relator else ""
    orgao = f", {c.orgao_judicante}" if c.orgao_judicante else ""
    human = f"TST, {c.numero_formatado or c.id}{relator}{orgao}".rstrip()
    return Citation(
        lex_uri=f"tst:{c.id}",
        human_readable_citation=human,
        source_url="https://jurisprudencia.tst.jus.br/",
    )


# ---------------------------------------------------------------------------
# TCU (pesquisa.apps.tcu.gov.br)
# ---------------------------------------------------------------------------


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(value: str | None) -> str | None:
    """Mechanically flatten the HTML the TCU backend returns for its prose
    fields (``ACORDAO``/``RELATORIO``/``VOTO``/``SUMARIO``) into plain text:
    tag removal + entity unescape + whitespace collapse. No summarising, no
    reordering - the words are the upstream's own, in the upstream's order.
    """
    if not value:
        return value
    text = _TAG_RE.sub(" ", html.unescape(value))
    return re.sub(r"\s+", " ", text).strip() or None


def parse_caso_tcu(raw: dict[str, Any]) -> CasoTCU:
    """Parse one document from the TCU ``documentosResumidos`` / ``documento``
    endpoints (same field names in both; the full-document endpoint adds
    ``ACORDAO``/``RELATORIO``/``VOTO``).
    """
    return CasoTCU(
        key=raw.get("KEY", ""),
        numero=raw.get("NUMACORDAO", ""),
        ano=raw.get("ANOACORDAO", ""),
        colegiado=raw.get("COLEGIADO"),
        titulo=raw.get("TITULO"),
        relator=raw.get("RELATOR"),
        situacao=raw.get("SITUACAO"),
        data_sessao=raw.get("DATASESSAO"),
        sumario=_strip_html(raw.get("SUMARIO")),
        acordao_texto=_strip_html(raw.get("ACORDAO")),
        relatorio=_strip_html(raw.get("RELATORIO")),
        voto=_strip_html(raw.get("VOTO")),
        url_arquivo_pdf=raw.get("URLARQUIVOPDF"),
    )


def build_caso_tcu_citation(c: CasoTCU) -> Citation:
    """`source_url` is the record's own ``URLARQUIVOPDF`` when the API
    returned one (upstream's own data, not a constructed URL); otherwise the
    human-facing search portal. `lex_uri` is the index's own stable ``KEY``.
    """
    relator = f", Rel. {c.relator}" if c.relator else ""
    colegiado = f" - {c.colegiado}" if c.colegiado else ""
    human = f"TCU, Acórdão {c.numero}/{c.ano}{colegiado}{relator}".rstrip()
    return Citation(
        lex_uri=f"tcu:{c.key}",
        human_readable_citation=human,
        source_url=c.url_arquivo_pdf or "https://pesquisa.apps.tcu.gov.br/pesquisa/jurisprudencia",
    )
