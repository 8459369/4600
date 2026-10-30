from dataclasses import dataclass


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
