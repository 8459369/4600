-- Dados de EXEMPLO para arrancar a aplicação: ajustar à realidade antes de usar.
-- Corre uma vez, depois de criar_base_dados.sql,
-- numa base vazia. Os códigos DICOFRE das 26 freguesias vêm da CAOP, através
-- de json.geoapi.pt (consultado em 2026-10-26); confirmar numa atualização da CAOP.

INSERT INTO tipo_organizacao (codigo, nome) VALUES
    ('autarquia', 'Autarquia'),
    ('junta_freguesia', 'Junta de freguesia'),
    ('educacao', 'Educação'),
    ('saude', 'Saúde'),
    ('solidariedade', 'Solidariedade social'),
    ('cultura', 'Cultura'),
    ('associacao', 'Associação'),
    ('turismo', 'Turismo e alojamento'),
    ('restauracao', 'Restauração'),
    ('industria', 'Indústria'),
    ('comercio', 'Comércio');

INSERT INTO freguesia (codigo_dicofre, nome) VALUES
    ('130103', 'Ansiães'),
    ('130107', 'Candemil'),
    ('130112', 'Fregim'),
    ('130115', 'Fridão'),
    ('130117', 'Gondar'),
    ('130118', 'Jazente'),
    ('130119', 'Lomba'),
    ('130120', 'Louredo'),
    ('130121', 'Lufrei'),
    ('130123', 'Mancelos'),
    ('130126', 'Padronelo'),
    ('130128', 'Rebordelo'),
    ('130129', 'Salvador do Monte'),
    ('130134', 'Gouveia (São Simão)'),
    ('130135', 'Telões'),
    ('130136', 'Travanca'),
    ('130138', 'Vila Caiz'),
    ('130139', 'Vila Chã do Marão'),
    ('130141', 'União das freguesias de Aboadela, Sanche e Várzea'),
    ('130142', 'União das freguesias de Amarante (São Gonçalo), Madalena, Cepelos e Gatão'),
    ('130143', 'União das freguesias de Bustelo, Carneiro e Carvalho de Rei'),
    ('130144', 'União das freguesias de Figueiró (Santiago e Santa Cristina)'),
    ('130145', 'União das freguesias de Freixo de Cima e de Baixo'),
    ('130146', 'União das freguesias de Olo e Canadelo'),
    ('130147', 'Vila Meã'),
    ('130148', 'União das freguesias de Vila Garcia, Aboim e Chapa');
