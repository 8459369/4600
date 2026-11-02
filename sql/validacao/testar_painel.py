import os

from flask import Flask
import psycopg

from observatorio import create_app


def principal() -> None:
    aplicacao = create_app()
    with psycopg.connect(os.environ["DATABASE_URL"]) as ligacao:
        organizacao_id = ligacao.execute(
            """
            SELECT id
            FROM organizacao
            WHERE nome = %s
            """,
            ("Teste coleta.4600.test",),
        ).fetchone()[0]

    with aplicacao.test_client() as cliente:
        assert cliente.get("/").status_code == 200
        percurso_anterior = cliente.post(
            f"/organizacoes/{organizacao_id}/dominios",
            data={"dominio": "novo.4600.test"},
            follow_redirects=True,
        )
        assert percurso_anterior.status_code == 200
        assert "novo.4600.test" in percurso_anterior.get_data(as_text=True)
        resposta = cliente.get(f"/organizacoes/{organizacao_id}")
        assert resposta.status_code == 200
        pagina = resposta.get_data(as_text=True)
        for texto in (
            "Recolhas DNS",
            "coleta.4600.test",
            "concluida",
            "parcial",
            "falhada",
            "Histórico",
            "192.0.2.10",
            "mail.4600.test",
            "v=spf1 -all",
        ):
            assert texto in pagina, texto

if __name__ == "__main__":
    principal()
    print("Painel e histórico validados.")
