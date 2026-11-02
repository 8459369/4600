from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any, Final

import psycopg
from flask import current_app
from psycopg.rows import class_row
from psycopg.types.json import Jsonb

from observatorio.modelos import (
    Ativo,
    Dominio,
    Ligacao,
    Observacao,
    Organizacao,
    Recolha,
    Seed,
)

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
    ligacao: psycopg.Connection,
    organizacao_id: int,
    dominio_id: int,
    motivo: str,
    modo: str = "passivo",
) -> bool:
    cursor = ligacao.execute(
        """
        INSERT INTO seed_descoberta (organizacao_id, dominio_id, modo, motivo)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (organizacao_id, dominio_id) DO NOTHING
        """,
        (organizacao_id, dominio_id, modo, motivo),
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


def obter_seed(ligacao: psycopg.Connection, seed_id: int) -> Seed | None:
    with ligacao.cursor(row_factory=class_row(Seed)) as cursor:
        cursor.execute(
            """
            SELECT seed_descoberta.id, seed_descoberta.organizacao_id,
                   seed_descoberta.dominio_id, dominio.nome AS dominio,
                   seed_descoberta.modo, seed_descoberta.motivo,
                   seed_descoberta.habilitada
            FROM seed_descoberta
            JOIN dominio ON dominio.id = seed_descoberta.dominio_id
            WHERE seed_descoberta.id = %s
            """,
            (seed_id,),
        )
        return cursor.fetchone()


def criar_recolha(
    ligacao: psycopg.Connection,
    seed_id: int,
    coletor: str,
    modo: str,
    iniciada_em: datetime | None = None,
) -> int:
    cursor = ligacao.execute(
        """
        INSERT INTO recolha (seed_id, coletor, modo, iniciada_em)
        VALUES (%s, %s, %s, COALESCE(%s, now()))
        RETURNING id
        """,
        (seed_id, coletor, modo, iniciada_em),
    )
    return _id_gerado(cursor)


def atualizar_recolha(
    ligacao: psycopg.Connection,
    recolha_id: int,
    estado: str,
    terminada_em: datetime | None,
    erro: str | None,
) -> None:
    cursor = ligacao.execute(
        """
        UPDATE recolha
        SET estado = %s, terminada_em = %s, erro = %s
        WHERE id = %s
        RETURNING id
        """,
        (estado, terminada_em, erro, recolha_id),
    )
    _id_gerado(cursor)


def garantir_ativo_dns(ligacao: psycopg.Connection, dominio_id: int) -> int:
    cursor = ligacao.execute(
        """
        INSERT INTO ativo (tipo, dominio_id)
        VALUES ('nome_dns', %s)
        ON CONFLICT (tipo, dominio_id) DO UPDATE
            SET dominio_id = EXCLUDED.dominio_id
        RETURNING id
        """,
        (dominio_id,),
    )
    return _id_gerado(cursor)


def garantir_ativo_ip(
    ligacao: psycopg.Connection, endereco_ip: str | IPv4Address | IPv6Address
) -> int:
    cursor = ligacao.execute(
        """
        INSERT INTO ativo (tipo, endereco_ip)
        VALUES ('endereco_ip', %s)
        ON CONFLICT (tipo, endereco_ip) DO UPDATE
            SET endereco_ip = EXCLUDED.endereco_ip
        RETURNING id
        """,
        (str(endereco_ip),),
    )
    return _id_gerado(cursor)


def obter_ativo(ligacao: psycopg.Connection, ativo_id: int) -> Ativo | None:
    with ligacao.cursor(row_factory=class_row(Ativo)) as cursor:
        cursor.execute(
            """
            SELECT ativo.id, ativo.tipo, ativo.dominio_id,
                   dominio.nome AS dominio, ativo.endereco_ip
            FROM ativo
            LEFT JOIN dominio ON dominio.id = ativo.dominio_id
            WHERE ativo.id = %s
            """,
            (ativo_id,),
        )
        return cursor.fetchone()


def criar_observacao(
    ligacao: psycopg.Connection,
    recolha_id: int,
    ativo_id: int,
    fonte: str,
    referencia: str,
    dados: Any,
    sucesso: bool,
    erro: str | None = None,
    observada_em: datetime | None = None,
) -> int:
    cursor = ligacao.execute(
        """
        INSERT INTO observacao (
            recolha_id, ativo_id, fonte, referencia, dados,
            sucesso, erro, observada_em
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, COALESCE(%s, now()))
        RETURNING id
        """,
        (
            recolha_id,
            ativo_id,
            fonte,
            referencia,
            Jsonb(dados),
            sucesso,
            erro,
            observada_em,
        ),
    )
    return _id_gerado(cursor)


def criar_ligacao(
    ligacao: psycopg.Connection,
    observacao_id: int,
    tipo: str,
    origem_ativo_id: int,
    destino_ativo_id: int,
) -> int:
    cursor = ligacao.execute(
        """
        INSERT INTO ligacao (
            observacao_id, tipo, origem_ativo_id, destino_ativo_id
        )
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (
            observacao_id, tipo, origem_ativo_id, destino_ativo_id
        ) DO UPDATE SET tipo = EXCLUDED.tipo
        RETURNING id
        """,
        (observacao_id, tipo, origem_ativo_id, destino_ativo_id),
    )
    return _id_gerado(cursor)


def obter_recolha(ligacao: psycopg.Connection, recolha_id: int) -> Recolha | None:
    with ligacao.cursor(row_factory=class_row(Recolha)) as cursor:
        cursor.execute(
            """
            SELECT id, seed_id, coletor, modo, estado,
                   iniciada_em, terminada_em, erro
            FROM recolha
            WHERE id = %s
            """,
            (recolha_id,),
        )
        return cursor.fetchone()


def listar_recolhas_seed(
    ligacao: psycopg.Connection, seed_id: int
) -> list[Recolha]:
    with ligacao.cursor(row_factory=class_row(Recolha)) as cursor:
        cursor.execute(
            """
            SELECT id, seed_id, coletor, modo, estado,
                   iniciada_em, terminada_em, erro
            FROM recolha
            WHERE seed_id = %s
            ORDER BY iniciada_em DESC, id DESC
            """,
            (seed_id,),
        )
        return cursor.fetchall()


def listar_observacoes_recolha(
    ligacao: psycopg.Connection, recolha_id: int
) -> list[Observacao]:
    with ligacao.cursor(row_factory=class_row(Observacao)) as cursor:
        cursor.execute(
            """
            SELECT id, recolha_id, ativo_id, fonte, referencia,
                   dados, sucesso, erro, observada_em
            FROM observacao
            WHERE recolha_id = %s
            ORDER BY id
            """,
            (recolha_id,),
        )
        return cursor.fetchall()


def listar_ligacoes_observacao(
    ligacao: psycopg.Connection, observacao_id: int
) -> list[Ligacao]:
    with ligacao.cursor(row_factory=class_row(Ligacao)) as cursor:
        cursor.execute(
            """
            SELECT id, observacao_id, tipo, origem_ativo_id, destino_ativo_id
            FROM ligacao
            WHERE observacao_id = %s
            ORDER BY id
            """,
            (observacao_id,),
        )
        return cursor.fetchall()
