"""Walk the normas.leg.br JSON-LD Legislation tree into an index and per-block text.

Tree shape (one node per Parte/Livro/Titulo/Capitulo/Secao/Artigo/paragrafo/...):

    {
      "workExample": {"name": "Art. 1o", "legislationIdentifier": "...@<date>!art1",
                       "text"?: "..."},
      "hasPart": <node> | [<node>, ...] | absent,
      "legislationIdentifier": "urn:lex:br:...;<numero>!art1",
      "legislationType": {"@id": ".../tipo-de-dispositivo/?urn=...:tipo.dispositivo:artigo"},
    }

`legislationIdentifier` (the one WITHOUT an `@<date>` version segment) carries the
addressable suffix after the last "!" - this is what callers pass back in as
`dispositivo` to fetch one block. `workExample.text` only appears on leaf nodes
(caput, paragrafo, inciso, alinea); container nodes (parte/livro/titulo/capitulo/
secao/artigo) hold their children in `hasPart` instead.

This module is an independent, clean-room implementation written directly against
the live API response (see DISCOVERY.md) - it does not reuse code from any
AGPL-licensed project.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DispositivoRef:
    """One addressable node in the Legislation tree (for the index)."""

    suffix: str
    tipo: str
    name: str | None


def _suffix(legislation_identifier: str) -> str:
    return legislation_identifier.rsplit("!", 1)[-1] if "!" in legislation_identifier else ""


def _tipo(node: dict) -> str:
    ltype = node.get("legislationType")
    if isinstance(ltype, dict):
        tipo_id = ltype.get("@id", "")
        return tipo_id.rsplit(":", 1)[-1] if ":" in tipo_id else tipo_id
    return ""


def _as_list(value: dict | list | None) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _work_example(node: dict) -> dict:
    """``workExample`` is usually one dict, occasionally a list of versions."""
    examples = _as_list(node.get("workExample"))
    return examples[0] if examples else {}


def _iter_nodes(node: dict):
    """Depth-first, document-order iteration over every node in the tree."""
    yield node
    for child in _as_list(node.get("hasPart")):
        yield from _iter_nodes(child)


def build_index(tree: dict) -> list[DispositivoRef]:
    """Flat, document-order list of every addressable node (headers + articles).

    Leaf-only nodes (caput/paragrafo/inciso/alinea, i.e. the text fragments
    inside one article) are excluded - address the parent artigo instead and
    `extract_text` concatenates its fragments in order.
    """
    refs: list[DispositivoRef] = []
    for node in _iter_nodes(tree):
        ident = node.get("legislationIdentifier", "")
        suffix = _suffix(ident)
        if not suffix:
            continue
        tipo = _tipo(node)
        if tipo in {"caput", "paragrafo", "inciso", "alinea", "item"}:
            continue
        work_example = _work_example(node)
        name = work_example.get("name")
        refs.append(DispositivoRef(suffix=suffix, tipo=tipo, name=name))
    return refs


def extract_text(tree: dict, suffix: str) -> str | None:
    """Concatenate the text of one dispositivo (e.g. ``"art1"``) and its children.

    Returns ``None`` if no node with that suffix exists in the tree.
    """
    target: dict | None = None
    for node in _iter_nodes(tree):
        if _suffix(node.get("legislationIdentifier", "")) == suffix:
            target = node
            break
    if target is None:
        return None

    parts: list[str] = []
    for node in _iter_nodes(target):
        work_example = _work_example(node)
        text = work_example.get("text")
        if text:
            parts.append(text.strip())
    return "\n".join(parts) if parts else None
