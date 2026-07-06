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
