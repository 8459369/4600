# Valida os dados, decide o que fazer e garante que as gravações acontecem
# todas ou nenhuma. Não escreve SQL: chama a camada de dados. É aqui que se
# abre a ligação, e cada "with ligar()" é uma transação.
from typing import Final

import psycopg

from observatorio import dados
from observatorio.dominios import normalizar_dominio
from observatorio.modelos import Dominio, Organizacao

# Código guardado na base de dados -> nome mostrado ao utilizador.
SETORES: Final = {"publico": "Público", "privado": "Privado", "social": "Social"}
TAMANHO_NOME: Final = 200
MOTIVO_SEED: Final = "Introduzido pelo operador"


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
        raise ErroValidacao("Nome é obrigatório.")
    if len(nome) > TAMANHO_NOME:
        raise ErroValidacao(f"Nome tem de ter no máximo {TAMANHO_NOME} caracteres.")
    if tipo_id is None:
        raise ErroValidacao("Escolha o tipo de organização.")
    if setor not in SETORES:
        raise ErroValidacao("Escolha o setor.")
    nif = nif.strip()
    if nif and not (nif.isascii() and nif.isdigit() and len(nif) == 9):
        raise ErroValidacao("O NIF tem de ter exatamente 9 dígitos.")

    with dados.ligar() as ligacao:
        if tipo_id not in {id for id, _ in dados.listar_tipos(ligacao)}:
            raise ErroValidacao("O tipo de organização escolhido não existe.")
        if freguesia_id is not None and freguesia_id not in {
            id for id, _ in dados.listar_freguesias(ligacao)
        }:
            raise ErroValidacao("A freguesia escolhida não existe.")
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
            "Indique só o nome do domínio, como 'exemplo.pt' , "
            "sem 'http://' ou 'www.' ou barras."
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
