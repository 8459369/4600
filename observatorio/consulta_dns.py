from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any, Protocol

import dns.exception
import dns.resolver

from observatorio.dominios import normalizar_dominio

TIPOS_REGISTO: tuple[str, ...] = ("A", "AAAA", "MX", "NS", "CNAME", "TXT")


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
    tipo: str
    dados: dict[str, Any]
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
    nome: str, tipo: str, resposta: Iterable[Any]
) -> tuple[dict[str, Any], list[LigacaoDNS]]:
    registos: list[dict[str, Any]] = []
    ligacoes: list[LigacaoDNS] = []
    for rdata in resposta:
        if tipo in {"A", "AAAA"}:
            endereco = str(getattr(rdata, "address"))
            endereco_ip = ip_address(endereco)
            if (tipo == "A" and endereco_ip.version != 4) or (
                tipo == "AAAA" and endereco_ip.version != 6
            ):
                raise ValueError(f"Resposta {tipo} com endereço incompatível")
            registos.append({"endereco": str(endereco_ip)})
            ligacoes.append(LigacaoDNS("aponta_para", str(endereco_ip), "ip"))
        elif tipo == "MX":
            destino = _nome_dns(getattr(rdata, "exchange"))
            registos.append(
                {"preferencia": int(getattr(rdata, "preference")), "troca": destino}
            )
            if destino != ".":
                ligacoes.append(LigacaoDNS("servidor_email", destino, "dns"))
        elif tipo in {"NS", "CNAME"}:
            destino = _nome_dns(getattr(rdata, "target"))
            registos.append({"destino": destino})
            # O tipo original fica nos dados; alias_de representa a relação
            # DNS para DNS no modelo atual.
            if destino != ".":
                ligacoes.append(LigacaoDNS("alias_de", destino, "dns"))
        else:
            partes = [_texto_txt(parte) for parte in getattr(rdata, "strings")]
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


def _dados_vazios(nome: str, tipo: str) -> dict[str, Any]:
    return {"nome": nome, "tipo": tipo, "registos": []}


def _texto_erro(erro: Exception) -> str:
    texto = str(erro).strip()
    return texto or erro.__class__.__name__
