from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any


@dataclass
class Organizacao:
    id: int
    nome: str
    nif: str | None
    tipo: str
    setor: str
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
    dados: Any
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
