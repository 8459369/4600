import os


def _variavel_obrigatoria(nome: str) -> str:
    valor = os.environ.get(nome)
    if not valor:
        raise RuntimeError(f"{nome} não está definida (ver .env.example)")
    return valor


def url_base_dados() -> str:
    return _variavel_obrigatoria("DATABASE_URL")


def chave_secreta() -> str:
    return _variavel_obrigatoria("SECRET_KEY")
