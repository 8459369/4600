#!/usr/bin/env bash
set -euo pipefail

raiz="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
nome="observatorio-validacao-$$"
porta="$((50000 + ($$ % 10000)))"

limpar() {
    podman rm --force "$nome" >/dev/null 2>&1 || true
}

trap limpar EXIT

podman run \
    --detach \
    --rm \
    --name "$nome" \
    --publish "$porta:5432" \
    -e POSTGRES_PASSWORD=validacao \
    -e POSTGRES_DB=observatorio \
    docker.io/library/postgres:17 >/dev/null

pronto=false
for tentativa in {1..60}; do
    if podman exec "$nome" pg_isready -U postgres -d observatorio >/dev/null 2>&1; then
        pronto=true
        break
    fi
    sleep 1
done

if [[ "$pronto" != true ]]; then
    echo "O PostgreSQL 17 não ficou disponível a tempo." >&2
    exit 1
fi

podman exec -i "$nome" psql -v ON_ERROR_STOP=1 -U postgres -d observatorio \
    < "$raiz/sql/criar_base_dados.sql"
podman exec -i "$nome" psql -v ON_ERROR_STOP=1 -U postgres -d observatorio \
    < "$raiz/sql/dados_iniciais.sql"
podman exec -i "$nome" psql -v ON_ERROR_STOP=1 -U postgres -d observatorio \
    < "$raiz/sql/validacao/testes_modelo.sql"

DATABASE_URL="postgresql://postgres:validacao@127.0.0.1:${porta}/observatorio" \
    SECRET_KEY=validacao \
    PYTHONPATH="$raiz" \
    python "$raiz/sql/validacao/testar_acesso.py"
PYTHONPATH="$raiz" python -m observatorio.recolher --help >/dev/null
DATABASE_URL="postgresql://postgres:validacao@127.0.0.1:${porta}/observatorio" \
    SECRET_KEY=validacao \
    PYTHONPATH="$raiz" \
    python "$raiz/sql/validacao/testar_coletor_dns.py"

echo "Validação do modelo concluída no PostgreSQL 17."
