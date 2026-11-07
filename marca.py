# -*- coding: utf-8 -*-
"""
Identidade do produto. Troque aqui e rode construir_instalador.bat de novo:
nome, versão, contato e cor são aplicados no programa, no ícone e no instalador.

Para usar a logo da empresa, salve um arquivo chamado logo.png (quadrado,
fundo transparente, 512x512 ou maior) nesta mesma pasta.
"""

EMPRESA = "Dirigível"
PRODUTO = "Dirigível Meet Guard"
NOME_CURTO = "Meet Guard"
VERSAO = "1.0.0"

SITE = "https://dirigivel.com.br"
EMAIL = "contato@dirigivel.com.br"

# Cor principal da marca (azul Dirigível). Formato #RRGGBB.
COR_PRINCIPAL = "#1C7BBA"

# ---- Não precisa mexer daqui para baixo ----
EXE = "MeetGuard"                       # nome do executável
NOME_TAREFA = "Dirigivel Meet Guard"    # tarefa "iniciar com o Windows"
PASTA_DADOS = "Dirigivel\\MeetGuard"    # dentro de %APPDATA%
# Identificador fixo do instalador: NÃO mude depois de distribuir,
# senão o Windows trata versões novas como outro programa.
APP_GUID = "14F2CEE7-E29B-4F01-95D9-4B0AFFB0EB3E"
