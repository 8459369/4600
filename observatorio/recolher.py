import argparse
import ipaddress
import sys

from dotenv import load_dotenv

from observatorio import create_app, servicos


def main(argumentos: list[str] | None = None) -> int:
    load_dotenv()
    parser = _criar_parser()
    opcoes = parser.parse_args(argumentos)
    try:
        nameservers = [str(ipaddress.ip_address(valor)) for valor in opcoes.nameserver]
    except ValueError as erro:
        parser.error(f"nameserver inválido: {erro}")

    aplicacao = create_app()
    with aplicacao.app_context():
        try:
            recolha = servicos.recolher_dns(
                opcoes.seed_id,
                timeout=opcoes.timeout,
                nameservers=nameservers,
            )
        except servicos.ErroValidacao as erro:
            print(f"Erro: {erro}", file=sys.stderr)
            return 2
        comparacoes = servicos.comparacoes_ignoradas_da_recolha(recolha.id)

    print(f"Recolha {recolha.id}: {recolha.estado}.")
    if recolha.erro:
        print(f"Erros: {recolha.erro}")
    for comparacao in comparacoes:
        print(
            f"Comparação de registos com a observação #{comparacao.observacao_anterior_id} "
            f"não feita: {comparacao.motivo}"
        )
    return 1 if recolha.estado == "falhada" else 0


def _criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Executa uma recolha DNS controlada para uma seed."
    )
    parser.add_argument("--seed-id", type=int, required=True)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument(
        "--nameserver",
        action="append",
        default=[],
        help="Endereço IP do resolvedor DNS; pode repetir-se.",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
