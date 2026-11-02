-- Observatório de Cibersegurança de Amarante — modelo de dados (PostgreSQL 17).
-- 10 tabelas: inventário, seeds, recolhas, evidência DNS e alterações.
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

-- Um ativo é uma identidade observável. O nome DNS reutiliza o domínio
-- canónico já existente; um endereço IP é guardado uma só vez, mesmo que
-- várias organizações ou recolhas o encontrem.
CREATE TABLE ativo (
    id SERIAL PRIMARY KEY,
    tipo VARCHAR(16) NOT NULL CHECK (tipo IN ('nome_dns', 'endereco_ip')),
    dominio_id INTEGER REFERENCES dominio (id) ON DELETE RESTRICT,
    endereco_ip INET,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (tipo = 'nome_dns' AND dominio_id IS NOT NULL AND endereco_ip IS NULL)
        OR (tipo = 'endereco_ip' AND dominio_id IS NULL AND endereco_ip IS NOT NULL)
    ),
    CHECK (
        endereco_ip IS NULL
        OR (family(endereco_ip) = 4 AND masklen(endereco_ip) = 32)
        OR (family(endereco_ip) = 6 AND masklen(endereco_ip) = 128)
    ),
    UNIQUE (tipo, dominio_id),
    UNIQUE (tipo, endereco_ip)
);

-- Cada execução é uma nova linha. Assim, uma falha posterior não apaga a
-- última evidência válida nem altera o histórico.
CREATE TABLE recolha (
    id SERIAL PRIMARY KEY,
    seed_id INTEGER NOT NULL REFERENCES seed_descoberta (id) ON DELETE RESTRICT,
    coletor VARCHAR(80) NOT NULL CHECK (btrim(coletor) <> ''),
    modo VARCHAR(12) NOT NULL CHECK (modo IN ('passivo', 'observacao')),
    estado VARCHAR(12) NOT NULL DEFAULT 'em_curso'
        CHECK (estado IN ('em_curso', 'concluida', 'parcial', 'falhada')),
    iniciada_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    terminada_em TIMESTAMPTZ,
    erro TEXT,
    CHECK (erro IS NULL OR btrim(erro) <> ''),
    CHECK (
        (estado = 'em_curso' AND terminada_em IS NULL)
        OR (estado <> 'em_curso' AND terminada_em IS NOT NULL)
    ),
    CHECK (terminada_em IS NULL OR terminada_em >= iniciada_em),
    CHECK (estado <> 'falhada' OR erro IS NOT NULL)
);

CREATE INDEX idx_recolha_seed_data
    ON recolha (seed_id, iniciada_em DESC);

-- A referência é estável dentro da fonte (por exemplo, o nome consultado e
-- o tipo DNS). A unicidade impede que a mesma evidência seja escrita duas
-- vezes na mesma recolha, mas permite que apareça em recolhas posteriores.
CREATE TABLE observacao (
    id SERIAL PRIMARY KEY,
    recolha_id INTEGER NOT NULL REFERENCES recolha (id) ON DELETE RESTRICT,
    ativo_id INTEGER NOT NULL REFERENCES ativo (id) ON DELETE RESTRICT,
    fonte VARCHAR(80) NOT NULL CHECK (btrim(fonte) <> ''),
    referencia VARCHAR(255) NOT NULL CHECK (btrim(referencia) <> ''),
    dados JSONB NOT NULL DEFAULT '{}'::jsonb,
    sucesso BOOLEAN NOT NULL,
    erro TEXT,
    observada_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (erro IS NULL OR btrim(erro) <> ''),
    CHECK (
        (sucesso AND erro IS NULL)
        OR (NOT sucesso AND erro IS NOT NULL)
    ),
    UNIQUE (recolha_id, fonte, referencia)
);

CREATE INDEX idx_observacao_recolha
    ON observacao (recolha_id, observada_em, id);

CREATE INDEX idx_observacao_ativo
    ON observacao (ativo_id, observada_em DESC);

-- As relações são observadas, não inferidas. Podem repetir-se em recolhas
-- diferentes, mas não duas vezes na mesma observação.
CREATE TABLE ligacao (
    id SERIAL PRIMARY KEY,
    observacao_id INTEGER NOT NULL REFERENCES observacao (id) ON DELETE RESTRICT,
    tipo VARCHAR(16) NOT NULL CHECK (
        tipo IN ('aponta_para', 'alias_de', 'servidor_email')
    ),
    origem_ativo_id INTEGER NOT NULL REFERENCES ativo (id) ON DELETE RESTRICT,
    destino_ativo_id INTEGER NOT NULL REFERENCES ativo (id) ON DELETE RESTRICT,
    CHECK (origem_ativo_id <> destino_ativo_id),
    UNIQUE (observacao_id, tipo, origem_ativo_id, destino_ativo_id)
);

CREATE INDEX idx_ligacao_origem
    ON ligacao (origem_ativo_id, id);

CREATE INDEX idx_ligacao_destino
    ON ligacao (destino_ativo_id, id);

-- Uma alteração compara duas observações bem-sucedidas do mesmo ativo.
-- A aplicação valida a compatibilidade entre as observações e só grava
-- diferenças que tenham evidência anterior e atual.
CREATE TABLE alteracao_ativo (
    id SERIAL PRIMARY KEY,
    observacao_anterior_id INTEGER NOT NULL REFERENCES observacao (id) ON DELETE RESTRICT,
    observacao_atual_id INTEGER NOT NULL REFERENCES observacao (id) ON DELETE RESTRICT,
    categoria VARCHAR(12) NOT NULL CHECK (categoria IN ('registo', 'ligacao')),
    tipo VARCHAR(12) NOT NULL CHECK (tipo IN ('adicionada', 'removida')),
    chave TEXT NOT NULL CHECK (btrim(chave) <> ''),
    dados JSONB NOT NULL DEFAULT '{}'::jsonb,
    criada_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (observacao_anterior_id <> observacao_atual_id),
    UNIQUE (
        observacao_anterior_id, observacao_atual_id,
        categoria, tipo, chave
    )
);

CREATE INDEX idx_alteracao_atual
    ON alteracao_ativo (observacao_atual_id, criada_em DESC);

CREATE INDEX idx_alteracao_anterior
    ON alteracao_ativo (observacao_anterior_id, criada_em DESC);
