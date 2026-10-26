"""
protocolo.py
-------------
Definicao do "PLP" (PUCRS Login Protocol) - protocolo de aplicacao
proprio, em texto claro, criado para este trabalho de laboratorio.

Formato das mensagens (terminadas em '\n', campos separados por espaco):

Cliente -> Servidor:
    LOGIN <usuario> <senha>
    QUIT

Servidor -> Cliente:
    200 OK <usuario>
    401 UNAUTHORIZED
    400 BAD_REQUEST
    BYE

Este protocolo e INTENCIONALMENTE inseguro: usuario e senha trafegam
em texto claro, sem nenhuma cifragem ou autenticacao de servidor.
Ele existe apenas para servir de alvo didatico nas Fases 1-3 do
trabalho de Laboratorio de Redes de Computadores.
"""

HOST_PADRAO = "0.0.0.0"
PORTA_PADRAO = 9999

# nem no codigo nem em transito (isso e justamente o que a Fase 3
# vai corrigir).
USUARIOS = {
    "Cadu": "senha123",
    "Goku": "testeteste",
    "Gohan": "trabalhoLabRedes",
}


def montar_login(usuario: str, senha: str) -> bytes:
    """Monta a mensagem de login do protocolo PLP."""
    msg = f"LOGIN {usuario} {senha}\n"
    return msg.encode("utf-8")


def montar_quit() -> bytes:
    return b"QUIT\n"


def interpretar_mensagem(linha: str):
    """
    Interpreta uma linha de protocolo recebida pelo servidor.
    Retorna uma tupla (comando, args).
    """
    partes = linha.strip().split(" ")
    if not partes or partes[0] == "":
        return None, []
    comando = partes[0].upper()
    args = partes[1:]
    return comando, args
