import os

import psycopg
from flask import Flask

from observatorio import create_app, servicos


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
            "Alterações observadas",
            "adicionada",
            "removida",
            "192.0.2.11",
        ):
            assert texto in pagina, texto
    _testar_gestao_organizacao(aplicacao)


def _testar_gestao_organizacao(aplicacao: Flask) -> None:
    with aplicacao.app_context():
        tipos, freguesias = servicos.opcoes_formulario()
        tipo_id = tipos[0][0]
        freguesia_id = freguesias[0][0]
        organizacao_id = servicos.registar_organizacao(
            "Gestão teste.4600.test", "", tipo_id, "privado", None
        )
        outra_id = servicos.registar_organizacao(
            "Outra gestão.4600.test", "500000000", tipo_id, "privado", None
        )
        servicos.associar_dominio(outra_id, "outra.4600.test")

    with aplicacao.test_client() as cliente:
        formulario = cliente.get(f"/organizacoes/{organizacao_id}/editar")
        assert formulario.status_code == 200
        pagina_formulario = formulario.get_data(as_text=True)
        assert "Editar organização" in pagina_formulario
        assert 'value="Gestão teste.4600.test"' in pagina_formulario

        dados_base = {
            "nome": "Gestão teste.4600.test",
            "nif": "",
            "tipo": tipo_id,
            "setor": "privado",
            "freguesia": "",
        }
        duplicado = cliente.post(
            f"/organizacoes/{organizacao_id}/editar",
            data={**dados_base, "nif": "500000000"},
        )
        assert duplicado.status_code == 422
        assert "Já existe uma organização com esse NIF" in duplicado.get_data(
            as_text=True
        )

        invalido = cliente.post(
            f"/organizacoes/{organizacao_id}/editar",
            data={**dados_base, "nif": "12345"},
        )
        assert invalido.status_code == 422
        assert "exatamente 9 dígitos" in invalido.get_data(as_text=True)

        atualizada = cliente.post(
            f"/organizacoes/{organizacao_id}/editar",
            data={
                "nome": "Gestão editada.4600.test",
                "nif": "600000000",
                "tipo": tipo_id,
                "setor": "publico",
                "freguesia": freguesia_id,
            },
            follow_redirects=True,
        )
        assert atualizada.status_code == 200
        pagina = atualizada.get_data(as_text=True)
        for texto in (
            "Organização atualizada.",
            "Gestão editada.4600.test",
            "600000000",
        ):
            assert texto in pagina, texto

        cliente.post(
            f"/organizacoes/{organizacao_id}/dominios",
            data={"dominio": "gestao.4600.test"},
        )
        with aplicacao.app_context():
            seed_id = servicos.obter_ficha_com_recolhas(organizacao_id)[2][0].id
            outra_seed_id = servicos.obter_ficha_com_recolhas(outra_id)[2][0].id

        desabilitada = cliente.post(
            f"/organizacoes/{organizacao_id}/seeds/{seed_id}/habilitacao",
            data={"habilitada": "0"},
            follow_redirects=True,
        )
        pagina = desabilitada.get_data(as_text=True)
        assert "Seed desabilitada." in pagina
        assert "Reabilitar" in pagina

        habilitada = cliente.post(
            f"/organizacoes/{organizacao_id}/seeds/{seed_id}/habilitacao",
            data={"habilitada": "1"},
            follow_redirects=True,
        )
        assert "Reabilitar" not in habilitada.get_data(as_text=True)

        cruzada = cliente.post(
            f"/organizacoes/{organizacao_id}/seeds/{outra_seed_id}/habilitacao",
            data={"habilitada": "0"},
            follow_redirects=True,
        )
        assert "A seed não existe nesta organização." in cruzada.get_data(as_text=True)

        sem_valor = cliente.post(
            f"/organizacoes/{organizacao_id}/seeds/{seed_id}/habilitacao",
            data={"habilitada": "2"},
        )
        assert sem_valor.status_code == 400


if __name__ == "__main__":
    principal()
    print("Painel e histórico validados.")
