from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any, Literal, Protocol, TypeAlias, TypedDict

import dns.exception
import dns.resolver

from observatorio.dominios import normalizar_dominio

TipoRegistoDNS: TypeAlias = Literal["A", "AAAA", "MX", "NS", "CNAME", "TXT"]
TIPOS_REGISTO: tuple[TipoRegistoDNS, ...] = (
    "A",
    "AAAA",
    "MX",
    "NS",
    "CNAME",
    "TXT",
)


class RegistoEndereco(TypedDict):
    endereco: str


class RegistoMX(TypedDict):
    preferencia: int
    troca: str


class RegistoDestino(TypedDict):
    destino: str


class RegistoTXT(TypedDict):
    partes: list[str]
    texto: str


RegistoDNS: TypeAlias = RegistoEndereco | RegistoMX | RegistoDestino | RegistoTXT


class DadosDNS(TypedDict):
    nome: str
    tipo: TipoRegistoDNS
    registos: list[RegistoDNS]


class ResolvedorDNS(Protocol):
    def resolve(
        self,
        nome: str,
        tipo: str,
        *,
        raise_on_no_answer: bool,
        lifetime: float,
    ) -> Iterable[Any]: ...


@dataclass(frozen=True)
class LigacaoDNS:
    tipo: str
    destino: str
    tipo_destino: str


@dataclass(frozen=True)
class ResultadoDNS:
    tipo: TipoRegistoDNS
    dados: DadosDNS
    sucesso: bool
    erro: str | None
    ligacoes: tuple[LigacaoDNS, ...]


def criar_resolvedor(
    timeout: float, nameservers: Sequence[str] | None = None
) -> dns.resolver.Resolver:
    if timeout <= 0:
        raise ValueError("O timeout DNS tem de ser maior do que zero.")
    resolvedor = dns.resolver.Resolver()
    resolvedor.timeout = timeout
    resolvedor.lifetime = timeout
    if nameservers:
        resolvedor.nameservers = list(nameservers)
    return resolvedor


def consultar_dominio(
    nome: str,
    resolvedor: ResolvedorDNS,
    timeout: float,
) -> list[ResultadoDNS]:
    resultados: list[ResultadoDNS] = []
    for tipo in TIPOS_REGISTO:
        try:
            resposta = resolvedor.resolve(
                nome,
                tipo,
                raise_on_no_answer=False,
                lifetime=timeout,
            )
            dados, ligacoes = _normalizar_resposta(nome, tipo, resposta)
            resultados.append(ResultadoDNS(tipo, dados, True, None, tuple(ligacoes)))
        except dns.resolver.NoAnswer:
            resultados.append(
                ResultadoDNS(tipo, _dados_vazios(nome, tipo), True, None, ())
            )
        except (dns.exception.DNSException, OSError, ValueError) as erro:
            resultados.append(
                ResultadoDNS(
                    tipo,
                    _dados_vazios(nome, tipo),
                    False,
                    _texto_erro(erro),
                    (),
                )
            )
    return resultados


def _normalizar_resposta(
    nome: str, tipo: TipoRegistoDNS, resposta: Iterable[Any]
) -> tuple[DadosDNS, list[LigacaoDNS]]:
    registos: list[RegistoDNS] = []
    ligacoes: list[LigacaoDNS] = []
    for rdata in resposta:
        if tipo in {"A", "AAAA"}:
            endereco = str(rdata.address)
            endereco_ip = ip_address(endereco)
            if (tipo == "A" and endereco_ip.version != 4) or (
                tipo == "AAAA" and endereco_ip.version != 6
            ):
                raise ValueError(f"Resposta {tipo} com endereço incompatível")
            registos.append({"endereco": str(endereco_ip)})
            ligacoes.append(LigacaoDNS("aponta_para", str(endereco_ip), "ip"))
        elif tipo == "MX":
            destino = _nome_dns(rdata.exchange)
            registos.append(
                {"preferencia": int(rdata.preference), "troca": destino}
            )
            if destino != ".":
                ligacoes.append(LigacaoDNS("servidor_email", destino, "dns"))
        elif tipo in {"NS", "CNAME"}:
            destino = _nome_dns(rdata.target)
            registos.append({"destino": destino})
            # O tipo original fica nos dados; alias_de representa a relação
            # DNS para DNS no modelo atual.
            if destino != ".":
                ligacoes.append(LigacaoDNS("alias_de", destino, "dns"))
        else:
            partes = [_texto_txt(parte) for parte in rdata.strings]
            registos.append({"partes": partes, "texto": "".join(partes)})
    return {"nome": nome, "tipo": tipo, "registos": registos}, ligacoes


def _nome_dns(valor: Any) -> str:
    texto = valor.to_text() if hasattr(valor, "to_text") else str(valor)
    if texto == ".":
        return texto
    nome = normalizar_dominio(texto)
    if nome is None:
        raise ValueError(f"Resposta DNS com nome inválido: {texto}")
    return nome


def _texto_txt(valor: Any) -> str:
    if isinstance(valor, bytes):
        return valor.decode("utf-8", errors="replace")
    return str(valor)


def _dados_vazios(nome: str, tipo: TipoRegistoDNS) -> DadosDNS:
    return {"nome": nome, "tipo": tipo, "registos": []}


def _texto_erro(erro: Exception) -> str:
    texto = str(erro).strip()
    return texto or erro.__class__.__name__
