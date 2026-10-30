-- Observatório de Cibersegurança de Amarante — modelo de dados (PostgreSQL 17).
-- 5 tabelas: organizações e os domínios que lhes servem de ponto de partida.
-- Este script cria uma base vazia; não é uma migração de dados existentes.

CREATE TABLE tipo_organizacao (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(30) NOT NULL UNIQUE,
    nome VARCHAR(80) NOT NULL
);

CREATE TABLE freguesia (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(120) NOT NULL,
    codigo_dicofre CHAR(6) NOT NULL UNIQUE
);

CREATE TABLE organizacao (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(200) NOT NULL,
    nif CHAR(9) UNIQUE,
    tipo_organizacao_id INTEGER NOT NULL REFERENCES tipo_organizacao (id),
    setor VARCHAR(10) NOT NULL CHECK (setor IN ('publico', 'privado', 'social')),
    freguesia_id INTEGER REFERENCES freguesia (id),
    origem VARCHAR(10) NOT NULL CHECK (origem IN ('manual', 'importada')),
    criada_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- O nome é guardado normalizado (minúsculas, IDNA convertido para ASCII pela
-- aplicação antes da inserção).
CREATE TABLE dominio (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(253) NOT NULL UNIQUE
        CHECK (nome ~ '^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$')
);

-- A seed é uma decisão explícita do operador, não uma inferência de posse.
CREATE TABLE seed_descoberta (
    id SERIAL PRIMARY KEY,
    organizacao_id INTEGER NOT NULL REFERENCES organizacao (id),
    dominio_id INTEGER NOT NULL REFERENCES dominio (id) ON DELETE RESTRICT,
    modo VARCHAR(12) NOT NULL CHECK (modo IN ('passivo', 'observacao')),
    -- Porque é que o operador escolheu este ponto de partida (ex.: site oficial).
    motivo VARCHAR(255) NOT NULL CHECK (btrim(motivo) <> ''),
    habilitada BOOLEAN NOT NULL DEFAULT true,
    criada_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (organizacao_id, dominio_id)
);
