from datetime import datetime, timezone
import os

from flask import Flask

from observatorio import dados


def principal() -> None:
    aplicacao = Flask(__name__)
    aplicacao.config["DATABASE_URL"] = os.environ["DATABASE_URL"]

    with aplicacao.app_context(), dados.ligar() as ligacao:
        seed = ligacao.execute(
            """
            SELECT id, dominio_id
            FROM seed_descoberta
            WHERE motivo = %s
            """,
            ("Teste do modelo",),
        ).fetchone()
        assert seed is not None

        seed_id, dominio_id = seed
        assert dados.obter_seed(ligacao, seed_id) is not None
        recolha_id = dados.criar_recolha(
            ligacao,
            seed_id,
            "smoke-python",
            "observacao",
            datetime.now(timezone.utc),
        )
        ativo_dns_id = dados.garantir_ativo_dns(ligacao, dominio_id)
        ativo_ip_id = dados.garantir_ativo_ip(ligacao, "198.51.100.5")
        assert dados.garantir_ativo_dns(ligacao, dominio_id) == ativo_dns_id
        assert dados.garantir_ativo_ip(ligacao, "198.51.100.5") == ativo_ip_id
        observacao_id = dados.criar_observacao(
            ligacao,
            recolha_id,
            ativo_dns_id,
            "dns",
            "validacao.4600.pt/A-python",
            {"registos": ["198.51.100.5"]},
            True,
        )
        ligacao_id = dados.criar_ligacao(
            ligacao,
            observacao_id,
            "aponta_para",
            ativo_dns_id,
            ativo_ip_id,
        )
        dados.atualizar_recolha(
            ligacao,
            recolha_id,
            "concluida",
            datetime.now(timezone.utc),
            None,
        )

        observacao = dados.listar_observacoes_recolha(ligacao, recolha_id)
        assert len(observacao) == 1
        assert observacao[0].dados == {"registos": ["198.51.100.5"]}
        assert dados.listar_ligacoes_observacao(ligacao, observacao_id)[0].id == ligacao_id
        assert dados.obter_recolha(ligacao, recolha_id).estado == "concluida"


if __name__ == "__main__":
    principal()
    print("Acesso parametrizado validado.")
