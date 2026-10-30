#########################################################################################
#                                                                                       #                                 
#  Normalização de nomes de domínio para a base de dados do Observatório.               #
#  Baseia-se na biblioteca idna, que implementa o algoritmo de normalização             #
#                                                                                       #                             
#########################################################################################

import idna

TAMANHO_MAXIMO = 253



def normalizar_dominio(texto: str) -> str | None:
    """Devolve o nome de domínio em minúsculas e em ASCII, ou None se o texto
    não for apenas um nome de domínio (por exemplo, um URL)."""
    nome = texto.strip().removesuffix(".")
    try:
        # uts46 passa para minúsculas e normaliza o Unicode; std3_rules recusa
        # ":", "/", "@", "_" e espaços, o que deixa os URLs de fora.
        nome = idna.encode(nome, uts46=True, std3_rules=True).decode("ascii")
    except idna.IDNAError:
        return None
    # A base de dados exige pelo menos dois rótulos ("amarante.pt").
    if "." not in nome or len(nome) > TAMANHO_MAXIMO:
        return None
    return nome
