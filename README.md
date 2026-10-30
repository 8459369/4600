# Observatório de Cibersegurança de Amarante

Projeto final da UFCD 5425. Ferramenta privada que regista as organizações de Amarante e os domínios que servem de ponto de partida para as recolhas.

Repositório: https://github.com/8459369/4600

## Requisitos

- Python 3.14 (versão em que foi testado)
- PostgreSQL 17
- Podman, só para a base de dados local dos exemplos abaixo

## Estrutura

| Local | Conteúdo |
| --- | --- |
| `observatorio/__init__.py` | Fábrica da aplicação Flask (`create_app`) |
| `observatorio/configuracao.py` | Leitura da configuração a partir do ambiente |
| `observatorio/rotas.py` | Rotas e respostas (camada de interface) |
| `observatorio/servicos.py` | Validação e transações |
| `observatorio/dados.py` | Acesso à base de dados (todo o SQL da aplicação) |
| `observatorio/modelos.py` | `Organizacao` e `Dominio` |
| `observatorio/dominios.py` | Normalização de nomes de domínio |
| `observatorio/templates/` | Páginas HTML (Jinja) |
| `sql/criar_base_dados.sql` | Modelo de dados (5 tabelas), para uma base vazia |
| `sql/dados_iniciais.sql` | Dados de exemplo: tipos de organização e as 26 freguesias de Amarante (DICOFRE) |


## Configuração

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `DATABASE_URL` | sim | URL de ligação ao PostgreSQL, por exemplo `postgresql://utilizador:palavra_passe@localhost:5432/observatorio` |
| `SECRET_KEY` | sim | Chave que assina as mensagens da sessão. Gerar com `python -c "import secrets; print(secrets.token_hex(32))"` |

Copiar `.env.example` para `.env`. O ficheiro está no `.gitignore`. O Flask carrega-o através do `python-dotenv`. Sem `DATABASE_URL` ou sem `SECRET_KEY` a aplicação não arranca e termina com `RuntimeError`.

## Instalação

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Preparar a base de dados

Exemplo com um PostgreSQL local em Podman (porta 5432, palavra-passe `teste`):

```sh
podman run -d --name observatorio-db -p 5432:5432 \
    -e POSTGRES_PASSWORD=teste -e POSTGRES_DB=observatorio \
    docker.io/library/postgres:17

podman exec -i observatorio-db psql -v ON_ERROR_STOP=1 -U postgres -d observatorio < sql/criar_base_dados.sql
podman exec -i observatorio-db psql -v ON_ERROR_STOP=1 -U postgres -d observatorio < sql/dados_iniciais.sql
```

Com `DATABASE_URL=postgresql://postgres:teste@localhost:5432/observatorio`.

Num servidor existente, aplicar os mesmos dois ficheiros por esta ordem com `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f <ficheiro>`. `criar_base_dados.sql` só serve para uma base vazia e não migra dados existentes.

## Executar

```sh
.venv/bin/python -m flask --app observatorio run
```

Serve em `http://127.0.0.1:5000`. É o servidor de desenvolvimento do Flask, não serve para produção.

| Método e caminho | Função |
| --- | --- |
| `GET /` | Lista de organizações |
| `GET`, `POST /organizacoes/nova` | Registar uma organização |
| `GET /organizacoes/<id>` | Ficha e domínios da organização |
| `POST /organizacoes/<id>/dominios` | Associar um domínio |

Não há autenticação nem proteção CSRF: a aplicação serve só uma máquina de confiança.
