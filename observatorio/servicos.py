# Valida os dados, decide o que fazer e garante que as gravações acontecem
# todas ou nenhuma. Não escreve SQL: chama a camada de dados. É aqui que se
# abre a ligação, e cada "with ligar()" é uma transação.
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Final

import psycopg

from observatorio import dados
from observatorio.consulta_dns import (
    LigacaoDNS,
    ResultadoDNS,
    ResolvedorDNS,
    TIPOS_REGISTO,
    consultar_dominio,
    criar_resolvedor,
)
from observatorio.dominios import normalizar_dominio
from observatorio.modelos import (
    Dominio,
    Organizacao,
    Recolha,
    RecolhaFicha,
    SeedFicha,
)

# Código guardado na base de dados -> nome mostrado ao utilizador.
SETORES: Final = {"publico": "Público", "privado": "Privado", "social": "Social"}
TAMANHO_NOME: Final = 200
MOTIVO_SEED: Final = "Introduzido pelo operador"
COLETOR_DNS: Final = "dns"


class ErroValidacao(Exception):
    # A mensagem é a que o utilizador lê.
    pass


def registar_organizacao(
    nome: str,
    nif: str,
    tipo_id: int | None,
    setor: str,
    freguesia_id: int | None,
) -> int:
    nome = nome.strip()
    if not nome:
        raise ErroValidacao("Indica o nome da organização.")
    if len(nome) > TAMANHO_NOME:
        raise ErroValidacao(
            f"Indica um nome com no máximo {TAMANHO_NOME} caracteres."
        )
    if tipo_id is None:
        raise ErroValidacao("Escolhe o tipo de organização.")
    if setor not in SETORES:
        raise ErroValidacao("Escolhe o setor.")
    nif = nif.strip()
    if nif and not (nif.isascii() and nif.isdigit() and len(nif) == 9):
        raise ErroValidacao("Indica um NIF com exatamente 9 dígitos.")

    with dados.ligar() as ligacao:
        if tipo_id not in {id for id, _ in dados.listar_tipos(ligacao)}:
            raise ErroValidacao("O tipo de organização que escolheste não existe.")
        if freguesia_id is not None and freguesia_id not in {
            id for id, _ in dados.listar_freguesias(ligacao)
        }:
            raise ErroValidacao("A freguesia que escolheste não existe.")
        try:
            return dados.criar_organizacao(
                ligacao, nome, nif or None, tipo_id, setor, freguesia_id
            )
        except psycopg.errors.UniqueViolation:
            raise ErroValidacao("Já existe uma organização com esse NIF associado.") from None


def associar_dominio(organizacao_id: int, texto: str) -> bool:
    """Devolve True se a associação é nova e False se já existia."""
    nome = normalizar_dominio(texto)
    if nome is None:
        raise ErroValidacao(
            "Indica apenas o nome do domínio, por exemplo 'exemplo.pt'. "
            "Não incluas 'http://', 'https://', caminhos ou parâmetros."
        )
    with dados.ligar() as ligacao:
        if dados.obter_organizacao(ligacao, organizacao_id) is None:
            raise ErroValidacao("A organização não existe.")
        dominio_id = dados.garantir_dominio(ligacao, nome)
        return dados.criar_seed(ligacao, organizacao_id, dominio_id, MOTIVO_SEED)


def listar_organizacoes() -> list[Organizacao]:
    with dados.ligar() as ligacao:
        return dados.listar_organizacoes(ligacao)


def opcoes_formulario() -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Devolve (tipos, freguesias), cada um como lista de (id, nome)."""
    with dados.ligar() as ligacao:
        return dados.listar_tipos(ligacao), dados.listar_freguesias(ligacao)


def obter_ficha(organizacao_id: int) -> tuple[Organizacao, list[Dominio]] | None:
    with dados.ligar() as ligacao:
        organizacao = dados.obter_organizacao(ligacao, organizacao_id)
        if organizacao is None:
            return None
        return organizacao, dados.listar_dominios(ligacao, organizacao_id)


def obter_ficha_com_recolhas(
    organizacao_id: int,
) -> tuple[Organizacao, list[Dominio], list[SeedFicha]] | None:
    with dados.ligar() as ligacao:
        organizacao = dados.obter_organizacao(ligacao, organizacao_id)
        if organizacao is None:
            return None
        seeds = []
        for seed in dados.listar_seeds_organizacao(ligacao, organizacao_id):
            recolhas = []
            for recolha in dados.listar_recolhas_seed(ligacao, seed.id):
                recolhas.append(
                    RecolhaFicha(
                        id=recolha.id,
                        seed_id=recolha.seed_id,
                        coletor=recolha.coletor,
                        modo=recolha.modo,
                        estado=recolha.estado,
                        iniciada_em=recolha.iniciada_em,
                        terminada_em=recolha.terminada_em,
                        erro=recolha.erro,
                        observacoes=dados.listar_observacoes_ficha(
                            ligacao, recolha.id
                        ),
                        ligacoes=dados.listar_ligacoes_ficha(ligacao, recolha.id),
                    )
                )
            seeds.append(
                SeedFicha(
                    id=seed.id,
                    dominio=seed.dominio,
                    modo=seed.modo,
                    motivo=seed.motivo,
                    habilitada=seed.habilitada,
                    recolhas=recolhas,
                )
            )
        return organizacao, dados.listar_dominios(ligacao, organizacao_id), seeds


def recolher_dns(
    seed_id: int,
    timeout: float = 3.0,
    nameservers: Sequence[str] | None = None,
    resolvedor: ResolvedorDNS | None = None,
) -> Recolha:
    """Executa uma recolha DNS e conserva cada tipo numa observação própria."""
    if timeout <= 0:
        raise ErroValidacao("O timeout DNS tem de ser maior do que zero.")

    with dados.ligar() as ligacao:
        seed = dados.obter_seed(ligacao, seed_id)
        if seed is None:
            raise ErroValidacao("A seed não existe.")
        if not seed.habilitada:
            raise ErroValidacao("A seed está desabilitada.")
        if seed.modo != "observacao":
            raise ErroValidacao(
                "A seed está em modo passivo; não foram feitos pedidos DNS."
            )
        recolha_id = dados.criar_recolha(
            ligacao, seed.id, COLETOR_DNS, "observacao"
        )

    try:
        if resolvedor is None:
            resolvedor = criar_resolvedor(timeout, nameservers)
        resultados = consultar_dominio(seed.dominio, resolvedor, timeout)
        estado, erro = _estado_recolha(resultados)
        with dados.ligar() as ligacao:
            ativo_origem_id = dados.garantir_ativo_dns(ligacao, seed.dominio_id)
            for resultado in resultados:
                observacao_id = dados.criar_observacao(
                    ligacao,
                    recolha_id,
                    ativo_origem_id,
                    COLETOR_DNS,
                    f"{seed.dominio}/{resultado.tipo}",
                    resultado.dados,
                    resultado.sucesso,
                    resultado.erro,
                )
                if resultado.sucesso:
                    _guardar_ligacoes(
                        ligacao, observacao_id, ativo_origem_id, resultado.ligacoes
                    )
            dados.atualizar_recolha(
                ligacao, recolha_id, estado, datetime.now(timezone.utc), erro
            )
            recolha = dados.obter_recolha(ligacao, recolha_id)
            if recolha is None:
                raise RuntimeError("A recolha desapareceu durante a gravação")
            return recolha
    except Exception as erro:
        _marcar_recolha_falhada(recolha_id, erro)
        raise


def _estado_recolha(resultados: Sequence[ResultadoDNS]) -> tuple[str, str | None]:
    falhas = [
        f"{resultado.tipo}: {resultado.erro}"
        for resultado in resultados
        if not resultado.sucesso
    ]
    if not falhas:
        return "concluida", None
    if len(falhas) == len(TIPOS_REGISTO):
        return "falhada", "; ".join(falhas)
    return "parcial", "; ".join(falhas)


def _guardar_ligacoes(
    ligacao: psycopg.Connection,
    observacao_id: int,
    origem_ativo_id: int,
    ligacoes: Sequence[LigacaoDNS],
) -> None:
    for relacao in ligacoes:
        if relacao.tipo_destino == "ip":
            destino_ativo_id = dados.garantir_ativo_ip(ligacao, relacao.destino)
        else:
            dominio_id = dados.garantir_dominio(ligacao, relacao.destino)
            destino_ativo_id = dados.garantir_ativo_dns(ligacao, dominio_id)
        dados.criar_ligacao(
            ligacao,
            observacao_id,
            relacao.tipo,
            origem_ativo_id,
            destino_ativo_id,
        )


def _marcar_recolha_falhada(recolha_id: int, erro: Exception) -> None:
    mensagem = str(erro).strip() or erro.__class__.__name__
    try:
        with dados.ligar() as ligacao:
            dados.atualizar_recolha(
                ligacao,
                recolha_id,
                "falhada",
                datetime.now(timezone.utc),
                mensagem,
            )
    except Exception as erro:
        raise RuntimeError("Não foi possível registar a falha da recolha") from erro
