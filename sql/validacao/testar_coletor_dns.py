import os
from dataclasses import dataclass
from datetime import datetime, timezone

import dns.exception
from flask import Flask

from observatorio import dados, servicos
from observatorio.consulta_dns import TIPOS_REGISTO
from observatorio.modelos import Observacao


@dataclass(frozen=True)
class NomeDNS:
    texto: str

    def to_text(self) -> str:
        return self.texto


@dataclass(frozen=True)
class Endereco:
    address: str


@dataclass(frozen=True)
class MX:
    preference: int
    exchange: NomeDNS


@dataclass(frozen=True)
class Alvo:
    target: NomeDNS


@dataclass(frozen=True)
class Texto:
    strings: tuple[bytes, ...]


class ResolvedorSimulado:
    def __init__(
        self,
        falhas: set[str] | None = None,
        respostas: dict[str, list[object]] | None = None,
    ) -> None:
        self.falhas = falhas or set()
        self.respostas = respostas or _respostas_base()
        self.chamadas: list[tuple[str, str, float]] = []

    def resolve(
        self,
        nome: str,
        tipo: str,
        *,
        raise_on_no_answer: bool,
        lifetime: float,
    ) -> list[object]:
        self.chamadas.append((nome, tipo, lifetime))
        if tipo in self.falhas:
            raise dns.exception.Timeout("timeout simulado")
        return self.respostas[tipo]


def _respostas_base() -> dict[str, list[object]]:
    return {
        "A": [Endereco("192.0.2.10")],
        "AAAA": [Endereco("2001:db8::10")],
        "MX": [
            MX(10, NomeDNS("mail.4600.test.")),
            MX(20, NomeDNS(".")),
        ],
        "NS": [Alvo(NomeDNS("ns.4600.test."))],
        "CNAME": [Alvo(NomeDNS("alias.4600.test."))],
        "TXT": [Texto((b"v=spf1 -all",))],
    }


def _respostas_alteradas() -> dict[str, list[object]]:
    respostas = _respostas_base()
    respostas.update(
        {
            "A": [Endereco("192.0.2.11")],
            "MX": [MX(10, NomeDNS("mail2.4600.test.")), MX(20, NomeDNS("."))],
            "CNAME": [],
            "TXT": [Texto((b"v=spf1 ~all",))],
        }
    )
    return respostas


def principal() -> None:
    _testar_evidencia_dns_invalida_falha()
    aplicacao = Flask(__name__)
    aplicacao.config["DATABASE_URL"] = os.environ["DATABASE_URL"]

    with aplicacao.app_context():
        seed_id = _criar_seed("coleta.4600.test", "observacao")
        _testar_recolha_concluida(seed_id)
        _testar_repeticao_sem_duplicar(seed_id)
        _testar_alteracoes(seed_id)
        _testar_falha_total_preserva_historico(seed_id)

        seed_parcial = _criar_seed("parcial.4600.test", "observacao")
        _testar_recolha_parcial(seed_parcial)

        seed_passiva = _criar_seed("passiva.4600.test", "passivo")
        _testar_seed_passiva(seed_passiva)


def _testar_evidencia_dns_invalida_falha() -> None:
    dados_invalidos = (
        {"nome": "coleta.4600.test", "tipo": "A"},
        {"nome": "coleta.4600.test", "tipo": "A", "registos": ["inválido"]},
    )
    for indice, payload in enumerate(dados_invalidos, start=1):
        observacao = Observacao(
            id=indice,
            recolha_id=1,
            ativo_id=1,
            fonte="dns",
            referencia="coleta.4600.test/A",
            dados=payload,
            sucesso=True,
            erro=None,
            observada_em=datetime.now(timezone.utc),
        )
        try:
            servicos._registos(observacao)
        except (TypeError, ValueError):
            continue
        raise AssertionError("A evidência DNS malformada foi aceite")


def _criar_seed(nome: str, modo: str) -> int:
    with dados.ligar() as ligacao:
        organizacao_id = ligacao.execute(
            """
            INSERT INTO organizacao (
                nome, tipo_organizacao_id, setor, origem
            )
            SELECT %s, id, 'privado', 'manual'
            FROM tipo_organizacao
            WHERE codigo = 'associacao'
            RETURNING organizacao.id
            """,
            (f"Teste {nome}",),
        ).fetchone()[0]
        dominio_id = dados.garantir_dominio(ligacao, nome)
        dados.criar_seed(
            ligacao,
            organizacao_id,
            dominio_id,
            "Teste do coletor DNS",
            modo,
        )
        return ligacao.execute(
            "SELECT id FROM seed_descoberta WHERE organizacao_id = %s",
            (organizacao_id,),
        ).fetchone()[0]


def _testar_recolha_concluida(seed_id: int) -> None:
    resolvedor = ResolvedorSimulado()
    recolha = servicos.recolher_dns(seed_id, timeout=0.5, resolvedor=resolvedor)
    assert recolha.estado == "concluida"
    assert [chamada[1] for chamada in resolvedor.chamadas] == list(TIPOS_REGISTO)

    with dados.ligar() as ligacao:
        observacoes = dados.listar_observacoes_recolha(ligacao, recolha.id)
        assert len(observacoes) == len(TIPOS_REGISTO)
        assert all(observacao.sucesso for observacao in observacoes)
        assert sum(
            len(dados.listar_ligacoes_observacao(ligacao, observacao.id))
            for observacao in observacoes
        ) == 5


def _testar_repeticao_sem_duplicar(seed_id: int) -> None:
    recolha = servicos.recolher_dns(
        seed_id, timeout=0.5, resolvedor=ResolvedorSimulado()
    )
    assert recolha.estado == "concluida"
    with dados.ligar() as ligacao:
        assert ligacao.execute(
            "SELECT count(*) FROM recolha WHERE seed_id = %s", (seed_id,)
        ).fetchone()[0] == 2
        assert ligacao.execute(
            """
            SELECT count(*)
            FROM ativo
            JOIN dominio ON dominio.id = ativo.dominio_id
            WHERE dominio.nome IN (
                'coleta.4600.test', 'mail.4600.test',
                'ns.4600.test', 'alias.4600.test'
            )
            """,
        ).fetchone()[0] == 4
        assert ligacao.execute(
            """
            SELECT count(*)
            FROM ativo
            WHERE tipo = 'endereco_ip'
              AND endereco_ip IN ('192.0.2.10', '2001:db8::10')
            """
        ).fetchone()[0] == 2
    assert _contar_alteracoes(seed_id) == 0


def _testar_alteracoes(seed_id: int) -> None:
    recolha = servicos.recolher_dns(
        seed_id,
        timeout=0.5,
        resolvedor=ResolvedorSimulado(respostas=_respostas_alteradas()),
    )
    assert recolha.estado == "concluida"

    total = _contar_alteracoes(seed_id)
    assert total > 0
    assert _contar_alteracoes(seed_id, "alteracao.tipo = 'adicionada'") > 0
    assert _contar_alteracoes(seed_id, "alteracao.tipo = 'removida'") > 0
    assert _contar_alteracoes(seed_id, "alteracao.categoria = 'registo'") > 0
    assert _contar_alteracoes(seed_id, "alteracao.categoria = 'ligacao'") > 0
    with dados.ligar() as ligacao:
        assert ligacao.execute(
            "SELECT count(*) FROM alteracao_ativo alteracao "
            "JOIN observacao atual ON atual.id = alteracao.observacao_atual_id "
            "JOIN recolha ON recolha.id = atual.recolha_id "
            "WHERE recolha.seed_id = %s GROUP BY "
            "alteracao.observacao_anterior_id, alteracao.observacao_atual_id, "
            "alteracao.categoria, alteracao.tipo, alteracao.chave "
            "HAVING count(*) > 1",
            (seed_id,),
        ).fetchall() == []

    total_anterior = total
    respostas_parciais = _respostas_alteradas()
    respostas_parciais["TXT"] = [Texto((b"v=spf1 ?all",))]
    recolha_parcial = servicos.recolher_dns(
        seed_id,
        timeout=0.5,
        resolvedor=ResolvedorSimulado(
            {"TXT"}, respostas=respostas_parciais
        ),
    )
    assert recolha_parcial.estado == "parcial"
    assert _contar_alteracoes(seed_id) == total_anterior

    servicos.recolher_dns(
        seed_id,
        timeout=0.5,
        resolvedor=ResolvedorSimulado(respostas=_respostas_alteradas()),
    )
    assert _contar_alteracoes(seed_id) == total_anterior


def _testar_recolha_parcial(seed_id: int) -> None:
    recolha = servicos.recolher_dns(
        seed_id,
        timeout=0.5,
        resolvedor=ResolvedorSimulado({"TXT"}),
    )
    assert recolha.estado == "parcial"
    assert recolha.erro is not None and "TXT" in recolha.erro


def _testar_falha_total_preserva_historico(seed_id: int) -> None:
    with dados.ligar() as ligacao:
        observacoes_anteriores = ligacao.execute(
            "SELECT count(*) FROM observacao o JOIN recolha r ON r.id = o.recolha_id "
            "WHERE r.seed_id = %s AND o.sucesso",
            (seed_id,),
        ).fetchone()[0]
    alteracoes_anteriores = _contar_alteracoes(seed_id)

    recolha = servicos.recolher_dns(
        seed_id,
        timeout=0.5,
        resolvedor=ResolvedorSimulado(set(TIPOS_REGISTO)),
    )
    assert recolha.estado == "falhada"

    with dados.ligar() as ligacao:
        assert ligacao.execute(
            "SELECT count(*) FROM observacao o JOIN recolha r ON r.id = o.recolha_id "
            "WHERE r.seed_id = %s AND o.sucesso",
            (seed_id,),
        ).fetchone()[0] == observacoes_anteriores
    assert _contar_alteracoes(seed_id) == alteracoes_anteriores


def _contar_alteracoes(seed_id: int, filtro: str | None = None) -> int:
    consulta = """
        SELECT count(*)
        FROM alteracao_ativo alteracao
        JOIN observacao atual ON atual.id = alteracao.observacao_atual_id
        JOIN recolha ON recolha.id = atual.recolha_id
        WHERE recolha.seed_id = %s
    """
    parametros: tuple[object, ...] = (seed_id,)
    if filtro:
        consulta += f" AND {filtro}"
    with dados.ligar() as ligacao:
        return ligacao.execute(consulta, parametros).fetchone()[0]


def _testar_seed_passiva(seed_id: int) -> None:
    resolvedor = ResolvedorSimulado()
    try:
        servicos.recolher_dns(seed_id, resolvedor=resolvedor)
    except servicos.ErroValidacao as erro:
        assert "passivo" in str(erro)
    else:
        raise AssertionError("A seed passiva foi aceite")
    assert resolvedor.chamadas == []
    with dados.ligar() as ligacao:
        assert ligacao.execute(
            "SELECT count(*) FROM recolha WHERE seed_id = %s", (seed_id,)
        ).fetchone()[0] == 0


if __name__ == "__main__":
    principal()
    print("Coletor DNS validado com respostas simuladas.")
