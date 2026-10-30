import os


def url_base_dados() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL não está definida (ver .env.example)")
    return url
