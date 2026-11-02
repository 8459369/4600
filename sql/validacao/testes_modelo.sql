\set ON_ERROR_STOP on

INSERT INTO organizacao (
    nome, tipo_organizacao_id, setor, origem
)
SELECT 'Organização de validação', id, 'privado', 'manual'
FROM tipo_organizacao
WHERE codigo = 'associacao'
RETURNING id AS organizacao_id \gset

INSERT INTO dominio (nome)
VALUES ('validacao.4600.pt')
RETURNING id AS dominio_id \gset

INSERT INTO seed_descoberta (
    organizacao_id, dominio_id, modo, motivo
)
VALUES (:organizacao_id, :dominio_id, 'observacao', 'Teste do modelo')
RETURNING id AS seed_id \gset

INSERT INTO ativo (tipo, dominio_id)
VALUES ('nome_dns', :dominio_id)
RETURNING id AS ativo_dns_id \gset

INSERT INTO ativo (tipo, endereco_ip)
VALUES ('endereco_ip', '192.0.2.10')
RETURNING id AS ativo_ip_id \gset

INSERT INTO recolha (
    seed_id, coletor, modo, estado, iniciada_em, terminada_em
)
VALUES (
    :seed_id, 'dns', 'observacao', 'concluida',
    now() - interval '1 minute', now()
)
RETURNING id AS recolha_id \gset

INSERT INTO observacao (
    recolha_id, ativo_id, fonte, referencia, dados, sucesso
)
VALUES (
    :recolha_id, :ativo_dns_id, 'dns', 'validacao.4600.pt/A',
    '{"registos":["192.0.2.10"]}'::jsonb, true
)
RETURNING id AS observacao_id \gset

INSERT INTO ligacao (
    observacao_id, tipo, origem_ativo_id, destino_ativo_id
)
VALUES (:observacao_id, 'aponta_para', :ativo_dns_id, :ativo_ip_id);

INSERT INTO observacao (
    recolha_id, ativo_id, fonte, referencia, dados, sucesso, erro
)
VALUES (
    :recolha_id, :ativo_dns_id, 'dns', 'validacao.4600.pt/TXT',
    '{}'::jsonb, false, 'Tempo limite'
);

-- Uma nova recolha conserva o histórico e pode reutilizar as mesmas
-- identidades sem criar um segundo ativo para o mesmo nome ou IP.
INSERT INTO recolha (
    seed_id, coletor, modo, estado, iniciada_em, terminada_em
)
VALUES (
    :seed_id, 'dns', 'observacao', 'concluida',
    now() - interval '30 seconds', now()
)
RETURNING id AS segunda_recolha_id \gset

INSERT INTO observacao (
    recolha_id, ativo_id, fonte, referencia, dados, sucesso
)
VALUES (
    :segunda_recolha_id, :ativo_dns_id, 'dns', 'validacao.4600.pt/A',
    '{"registos":["192.0.2.10"]}'::jsonb, true
);

INSERT INTO ativo (tipo, endereco_ip)
VALUES ('endereco_ip', '192.0.2.10')
ON CONFLICT (tipo, endereco_ip) DO NOTHING;

DO $$
DECLARE
    id_seed INTEGER;
    id_observacao INTEGER;
BEGIN
    SELECT id INTO id_seed
    FROM seed_descoberta
    WHERE motivo = 'Teste do modelo';

    SELECT id INTO id_observacao
    FROM observacao
    WHERE referencia = 'validacao.4600.pt/A'
    ORDER BY id
    LIMIT 1;

    IF (SELECT count(*) FROM recolha WHERE seed_id = id_seed) <> 2 THEN
        RAISE EXCEPTION 'O histórico de recolhas não foi conservado';
    END IF;
    IF (SELECT count(*) FROM ativo WHERE tipo = 'nome_dns') <> 1 THEN
        RAISE EXCEPTION 'O nome DNS foi duplicado';
    END IF;
    IF (SELECT count(*) FROM ativo WHERE tipo = 'endereco_ip') <> 1 THEN
        RAISE EXCEPTION 'O endereço IP foi duplicado';
    END IF;
    IF (SELECT count(*) FROM ligacao WHERE observacao_id = id_observacao) <> 1 THEN
        RAISE EXCEPTION 'A ligação DNS não foi conservada';
    END IF;
END
$$;

DO $$
DECLARE
    id_seed INTEGER;
    id_recolha INTEGER;
    id_observacao INTEGER;
    id_ativo_dns INTEGER;
    id_ativo_ip INTEGER;
BEGIN
    SELECT id INTO id_seed
    FROM seed_descoberta
    WHERE motivo = 'Teste do modelo';

    SELECT id INTO id_recolha
    FROM recolha
    ORDER BY id
    LIMIT 1;

    SELECT id INTO id_observacao
    FROM observacao
    WHERE referencia = 'validacao.4600.pt/A'
    ORDER BY id
    LIMIT 1;

    SELECT id INTO id_ativo_dns
    FROM ativo
    WHERE tipo = 'nome_dns';

    SELECT id INTO id_ativo_ip
    FROM ativo
    WHERE tipo = 'endereco_ip';

    BEGIN
        INSERT INTO recolha (
            seed_id, coletor, modo, estado, iniciada_em, terminada_em
        )
        VALUES (999999, 'dns', 'observacao', 'concluida', now(), now());
        RAISE EXCEPTION 'Foi aceite uma seed inexistente';
    EXCEPTION WHEN foreign_key_violation THEN
        NULL;
    END;

    BEGIN
        INSERT INTO observacao (
            recolha_id, ativo_id, fonte, referencia, dados, sucesso
        )
        VALUES (id_recolha, 999999, 'dns', 'referencia-invalida', '{}', true);
        RAISE EXCEPTION 'Foi aceite um ativo inexistente';
    EXCEPTION WHEN foreign_key_violation THEN
        NULL;
    END;

    BEGIN
        INSERT INTO observacao (
            recolha_id, ativo_id, fonte, referencia, dados, sucesso, erro
        )
        VALUES (id_recolha, id_ativo_dns, 'dns', 'estado-invalido', '{}', true, 'erro');
        RAISE EXCEPTION 'Foi aceite uma observação contraditória';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;

    BEGIN
        INSERT INTO ativo (tipo)
        VALUES ('nome_dns');
        RAISE EXCEPTION 'Foi aceite um ativo sem identidade';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;

    BEGIN
        INSERT INTO ativo (tipo, endereco_ip)
        VALUES ('endereco_ip', '192.0.2.0/24');
        RAISE EXCEPTION 'Foi aceite uma rede como endereço IP';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;

    BEGIN
        INSERT INTO recolha (
            seed_id, coletor, modo, estado, iniciada_em, terminada_em
        )
        VALUES (id_seed, 'dns', 'observacao', 'falhada', now(), now());
        RAISE EXCEPTION 'Foi aceite uma recolha falhada sem erro';
    EXCEPTION WHEN check_violation THEN
        NULL;
    END;

    BEGIN
        INSERT INTO ligacao (
            observacao_id, tipo, origem_ativo_id, destino_ativo_id
        )
        VALUES (id_observacao, 'aponta_para', id_ativo_dns, id_ativo_ip);
        RAISE EXCEPTION 'Foi aceite uma ligação duplicada';
    EXCEPTION WHEN unique_violation THEN
        NULL;
    END;
END
$$;

SELECT 'modelo válido' AS resultado;
