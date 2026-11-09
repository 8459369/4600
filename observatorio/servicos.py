# Valida os dados, decide o que fazer e garante que as gravações acontecem
# todas ou nenhuma. Não escreve SQL: chama a camada de dados. É aqui que se
# abre a ligação, e cada "with ligar()" é uma transação.
import json
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Final

import psycopg

from observatorio import dados
from observatorio.consulta_dns import (
    TIPOS_REGISTO,
    LigacaoDNS,
    ResolvedorDNS,
    ResultadoDNS,
    consultar_dominio,
    criar_resolvedor,
)
from observatorio.dominios import normalizar_dominio
from observatorio.modelos import (
    AlteracaoFicha,
    ComparacaoIgnorada,
    Dominio,
    JsonObject,
    LigacaoFicha,
    Observacao,
    ObservacaoFicha,
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


class HistoricoIlegivel(Exception):
    # Evidência anterior que a comparação não consegue ler. Não impede a
    # recolha nova; a ficha mostra a comparação que ficou por fazer.
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
        seeds_db = dados.listar_seeds_organizacao(ligacao, organizacao_id)
        seed_ids = [seed.id for seed in seeds_db]
        recolhas_db = dados.listar_recolhas_seeds(ligacao, seed_ids)
        recolha_ids = [recolha.id for recolha in recolhas_db]

        recolhas_por_seed: dict[int, list[Recolha]] = {
            seed_id: [] for seed_id in seed_ids
        }
        for recolha in recolhas_db:
            recolhas_por_seed[recolha.seed_id].append(recolha)

        observacoes_por_recolha: dict[int, list[ObservacaoFicha]] = {
            recolha_id: [] for recolha_id in recolha_ids
        }
        for observacao in dados.listar_observacoes_ficha_recolhas(
            ligacao, recolha_ids
        ):
            observacoes_por_recolha[observacao.recolha_id].append(observacao)

        ligacoes_por_recolha: dict[int, list[LigacaoFicha]] = {
            recolha_id: [] for recolha_id in recolha_ids
        }
        for ligacao_ficha in dados.listar_ligacoes_ficha_recolhas(
            ligacao, recolha_ids
        ):
            ligacoes_por_recolha[ligacao_ficha.recolha_id].append(ligacao_ficha)

        alteracoes_por_seed: dict[int, list[AlteracaoFicha]] = {
            seed_id: [] for seed_id in seed_ids
        }
        for alteracao in dados.listar_alteracoes_ficha_seeds(ligacao, seed_ids):
            alteracoes_por_seed[alteracao.seed_id].append(alteracao)

        seeds: list[SeedFicha] = []
        for seed in seeds_db:
            observacoes_seed = [
                observacao
                for recolha in recolhas_por_seed[seed.id]
                for observacao in observacoes_por_recolha[recolha.id]
            ]
            comparacoes_seed = _comparacoes_ignoradas(observacoes_seed)
            recolhas: list[RecolhaFicha] = []
            for recolha in recolhas_por_seed[seed.id]:
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
                        observacoes=observacoes_por_recolha[recolha.id],
                        ligacoes=ligacoes_por_recolha[recolha.id],
                        comparacoes_ignoradas=[
                            comparacao
                            for comparacao in comparacoes_seed
                            if comparacao.recolha_id == recolha.id
                        ],
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
                    alteracoes=alteracoes_por_seed[seed.id],
                )
            )
        dominios = dados.listar_dominios(ligacao, organizacao_id)
        return organizacao, dominios, seeds


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
            _registar_alteracoes(ligacao, seed.id, recolha_id)
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


def _registar_alteracoes(
    ligacao: psycopg.Connection, seed_id: int, recolha_id: int
) -> None:
    for atual in dados.listar_observacoes_recolha(ligacao, recolha_id):
        if not atual.sucesso:
            continue
        anterior = dados.obter_observacao_anterior_sucesso(
            ligacao, seed_id, atual.id
        )
        if anterior is None:
            continue
        if _motivo_historico_ilegivel(anterior.id, anterior.dados) is None:
            _comparar_registos(ligacao, anterior, atual)
        _comparar_ligacoes(ligacao, anterior, atual)


def _comparacoes_ignoradas(
    observacoes: Sequence[ObservacaoFicha],
) -> list[ComparacaoIgnorada]:
    """Lista as comparações que a recolha não fez, a partir dos dados guardados.

    Segue a regra de `obter_observacao_anterior_sucesso`: a anterior é a última
    observação com sucesso, da mesma fonte, referência e ativo, observada antes
    da atual.
    """
    ultima_por_chave: dict[tuple[str, str, str], ObservacaoFicha] = {}
    ignoradas: list[ComparacaoIgnorada] = []
    for atual in sorted(observacoes, key=lambda obs: (obs.observada_em, obs.id)):
        if not atual.sucesso:
            continue
        chave = (atual.ativo, atual.fonte, atual.referencia)
        anterior = ultima_por_chave.get(chave)
        ultima_por_chave[chave] = atual
        if anterior is None:
            continue
        motivo = _motivo_historico_ilegivel(anterior.id, anterior.dados)
        if motivo is not None:
            ignoradas.append(
                ComparacaoIgnorada(
                    recolha_id=atual.recolha_id,
                    observacao_anterior_id=anterior.id,
                    motivo=motivo,
                )
            )
    return ignoradas


def _motivo_historico_ilegivel(
    observacao_id: int, dados_observacao: JsonObject
) -> str | None:
    try:
        _registos(observacao_id, dados_observacao)
    except HistoricoIlegivel as erro:
        return str(erro)
    return None


def _comparar_registos(
    ligacao: psycopg.Connection,
    anterior: Observacao,
    atual: Observacao,
) -> None:
    anteriores = _registos(anterior.id, anterior.dados)
    atuais = _registos(atual.id, atual.dados)
    _guardar_diferencas(
        ligacao,
        anterior,
        atual,
        "registo",
        anteriores,
        atuais,
    )


def _comparar_ligacoes(
    ligacao: psycopg.Connection,
    anterior: Observacao,
    atual: Observacao,
) -> None:
    anteriores = _ligacoes(ligacao, anterior.id)
    atuais = _ligacoes(ligacao, atual.id)
    _guardar_diferencas(
        ligacao,
        anterior,
        atual,
        "ligacao",
        anteriores,
        atuais,
    )


def _guardar_diferencas(
    ligacao: psycopg.Connection,
    anterior: Observacao,
    atual: Observacao,
    categoria: str,
    anteriores: dict[str, JsonObject],
    atuais: dict[str, JsonObject],
) -> None:
    for chave in sorted(atuais.keys() - anteriores.keys()):
        dados.criar_alteracao(
            ligacao,
            anterior.id,
            atual.id,
            categoria,
            "adicionada",
            chave,
            atuais[chave],
        )
    for chave in sorted(anteriores.keys() - atuais.keys()):
        dados.criar_alteracao(
            ligacao,
            anterior.id,
            atual.id,
            categoria,
            "removida",
            chave,
            anteriores[chave],
        )


def _registos(
    observacao_id: int, dados_observacao: JsonObject
) -> dict[str, JsonObject]:
    if not isinstance(dados_observacao, dict):
        raise HistoricoIlegivel(
            f"Os dados da observação {observacao_id} não são um objeto JSON."
        )

    nome = dados_observacao.get("nome")
    tipo = dados_observacao.get("tipo")
    registos = dados_observacao.get("registos")
    if (
        not isinstance(nome, str)
        or not isinstance(tipo, str)
        or tipo not in TIPOS_REGISTO
        or not isinstance(registos, list)
    ):
        raise HistoricoIlegivel(
            f"Os dados DNS da observação {observacao_id} têm uma estrutura inválida."
        )

    resultado: dict[str, JsonObject] = {}
    for registo in registos:
        if not isinstance(registo, dict):
            raise HistoricoIlegivel(
                f"A observação {observacao_id} contém um registo DNS inválido."
            )
        resultado[_chave_json(registo)] = registo
    return resultado


def _ligacoes(
    ligacao: psycopg.Connection, observacao_id: int
) -> dict[str, JsonObject]:
    resultado: dict[str, JsonObject] = {}
    for relacao in dados.listar_ligacoes_ficha_observacao(ligacao, observacao_id):
        valor: JsonObject = {
            "tipo": relacao.tipo,
            "origem": relacao.origem,
            "destino": relacao.destino,
        }
        resultado[_chave_json(valor)] = valor
    return resultado


def _chave_json(valor: object) -> str:
    return json.dumps(
        valor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


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
    except Exception as erro_gravacao:
        raise RuntimeError(
            "Não foi possível registar a falha da recolha"
        ) from erro_gravacao
