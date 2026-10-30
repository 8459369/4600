from typing import Final

import psycopg
from flask import current_app
from psycopg.rows import class_row

from observatorio.modelos import Dominio, Organizacao

# LEFT JOIN na freguesia porque a organização pode não ter freguesia.
SELECT_ORGANIZACOES: Final = """
    SELECT organizacao.id, organizacao.nome, organizacao.nif,
           tipo_organizacao.nome AS tipo, organizacao.setor,
           freguesia.nome AS freguesia
    FROM organizacao
    JOIN tipo_organizacao ON tipo_organizacao.id = organizacao.tipo_organizacao_id
    LEFT JOIN freguesia ON freguesia.id = organizacao.freguesia_id
"""


def ligar() -> psycopg.Connection:
    # Usada num bloco "with": confirma no fim e desfaz tudo se houver um erro.
    return psycopg.connect(current_app.config["DATABASE_URL"])


def _id_gerado(cursor: psycopg.Cursor) -> int:
    linha = cursor.fetchone()
    if linha is None:
        raise RuntimeError("A base de dados não devolveu o identificador")
    return linha[0]


def listar_tipos(ligacao: psycopg.Connection) -> list[tuple[int, str]]:
    return ligacao.execute("SELECT id, nome FROM tipo_organizacao ORDER BY nome").fetchall()


def listar_freguesias(ligacao: psycopg.Connection) -> list[tuple[int, str]]:
    return ligacao.execute("SELECT id, nome FROM freguesia ORDER BY nome").fetchall()


def criar_organizacao(
    ligacao: psycopg.Connection,
    nome: str,
    nif: str | None,
    tipo_organizacao_id: int,
    setor: str,
    freguesia_id: int | None,
) -> int:
    cursor = ligacao.execute(
        """
        INSERT INTO organizacao (nome, nif, tipo_organizacao_id, setor, freguesia_id, origem)
        VALUES (%s, %s, %s, %s, %s, 'manual')
        RETURNING id
        """,
        (nome, nif, tipo_organizacao_id, setor, freguesia_id),
    )
    return _id_gerado(cursor)


def listar_organizacoes(ligacao: psycopg.Connection) -> list[Organizacao]:
    with ligacao.cursor(row_factory=class_row(Organizacao)) as cursor:
        cursor.execute(SELECT_ORGANIZACOES + " ORDER BY organizacao.nome")
        return cursor.fetchall()


def obter_organizacao(ligacao: psycopg.Connection, organizacao_id: int) -> Organizacao | None:
    with ligacao.cursor(row_factory=class_row(Organizacao)) as cursor:
        cursor.execute(SELECT_ORGANIZACOES + " WHERE organizacao.id = %s", (organizacao_id,))
        return cursor.fetchone()


def garantir_dominio(ligacao: psycopg.Connection, nome: str) -> int:
    # O DO UPDATE não muda nada: existe só para o RETURNING devolver o id
    # também quando o domínio já existia (com DO NOTHING não devolveria nada).
    cursor = ligacao.execute(
        """
        INSERT INTO dominio (nome) VALUES (%s)
        ON CONFLICT (nome) DO UPDATE SET nome = EXCLUDED.nome
        RETURNING id
        """,
        (nome,),
    )
    return _id_gerado(cursor)


def criar_seed(
    ligacao: psycopg.Connection, organizacao_id: int, dominio_id: int, motivo: str
) -> bool:
    # "passivo" é o modo mais restritivo: esta fase não faz chamadas de rede.
    cursor = ligacao.execute(
        """
        INSERT INTO seed_descoberta (organizacao_id, dominio_id, modo, motivo)
        VALUES (%s, %s, 'passivo', %s)
        ON CONFLICT (organizacao_id, dominio_id) DO NOTHING
        """,
        (organizacao_id, dominio_id, motivo),
    )
    return cursor.rowcount == 1


def listar_dominios(ligacao: psycopg.Connection, organizacao_id: int) -> list[Dominio]:
    with ligacao.cursor(row_factory=class_row(Dominio)) as cursor:
        cursor.execute(
            """
            SELECT dominio.id, dominio.nome
            FROM dominio
            JOIN seed_descoberta ON seed_descoberta.dominio_id = dominio.id
            WHERE seed_descoberta.organizacao_id = %s
            ORDER BY dominio.nome
            """,
            (organizacao_id,),
        )
        return cursor.fetchall()
