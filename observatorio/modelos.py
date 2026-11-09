from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import TypeAlias

JsonObject: TypeAlias = Mapping[str, object]


@dataclass
class Organizacao:
    id: int
    nome: str
    nif: str | None
    tipo_id: int
    tipo: str
    setor: str
    freguesia_id: int | None
    freguesia: str | None


@dataclass
class Dominio:
    id: int
    nome: str


@dataclass
class Seed:
    id: int
    organizacao_id: int
    dominio_id: int
    dominio: str
    modo: str
    motivo: str
    habilitada: bool


@dataclass
class Ativo:
    id: int
    tipo: str
    dominio_id: int | None
    dominio: str | None
    endereco_ip: IPv4Address | IPv6Address | None


@dataclass
class Recolha:
    id: int
    seed_id: int
    coletor: str
    modo: str
    estado: str
    iniciada_em: datetime
    terminada_em: datetime | None
    erro: str | None


@dataclass
class Observacao:
    id: int
    recolha_id: int
    ativo_id: int
    fonte: str
    referencia: str
    dados: JsonObject
    sucesso: bool
    erro: str | None
    observada_em: datetime


@dataclass
class Ligacao:
    id: int
    observacao_id: int
    tipo: str
    origem_ativo_id: int
    destino_ativo_id: int


@dataclass
class ObservacaoFicha:
    id: int
    recolha_id: int
    fonte: str
    referencia: str
    ativo: str
    dados: JsonObject
    sucesso: bool
    erro: str | None
    observada_em: datetime


@dataclass
class LigacaoFicha:
    id: int
    recolha_id: int
    observacao_id: int
    tipo: str
    origem: str
    destino: str


@dataclass
class AlteracaoFicha:
    id: int
    seed_id: int
    referencia: str
    categoria: str
    tipo: str
    dados: JsonObject
    recolha_anterior_id: int
    recolha_atual_id: int
    anterior_observada_em: datetime
    atual_observada_em: datetime


@dataclass
class ComparacaoIgnorada:
    recolha_id: int
    observacao_anterior_id: int
    motivo: str


@dataclass
class RecolhaFicha:
    id: int
    seed_id: int
    coletor: str
    modo: str
    estado: str
    iniciada_em: datetime
    terminada_em: datetime | None
    erro: str | None
    observacoes: list[ObservacaoFicha]
    ligacoes: list[LigacaoFicha]
    comparacoes_ignoradas: list[ComparacaoIgnorada]


@dataclass
class SeedFicha:
    id: int
    dominio: str
    modo: str
    motivo: str
    habilitada: bool
    recolhas: list[RecolhaFicha]
    alteracoes: list[AlteracaoFicha]
