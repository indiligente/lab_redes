#!/usr/bin/env python3
"""
cliente.py
-----------
Cliente do protocolo PLP.

Roda na VM-cliente. Conecta no servidor via TCP e envia um LOGIN em
texto claro, exatamente como especificado pelo protocolo da Fase 1.

Uso:
    python3 cliente.py <ip_servidor> <porta> <usuario> <senha>

Exemplo (na VM-cliente, supondo que o servidor esta em 192.168.56.11):
    python3 cliente.py 192.168.56.11 9999 alice senha123

Se usuario/senha nao forem passados por linha de comando, o cliente
pergunta interativamente (sem mascarar a senha - de proposito, para
deixar claro que ela trafega em texto claro).
"""

import socket
import sys

from protocolo import PORTA_PADRAO, montar_login, montar_quit


def main():
    if len(sys.argv) < 2:
        print(f"Uso: python3 {sys.argv[0]} <ip_servidor> [porta] [usuario] [senha]")
        sys.exit(1)

    ip_servidor = sys.argv[1]
    porta = int(sys.argv[2]) if len(sys.argv) > 2 else PORTA_PADRAO
    usuario = sys.argv[3] if len(sys.argv) > 3 else input("Usuario: ")
    senha = sys.argv[4] if len(sys.argv) > 4 else input("Senha: ")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as cliente:
        print(f"Conectando a {ip_servidor}:{porta} ...")
        cliente.connect((ip_servidor, porta))

        # O buffer preserva os dados entre leituras ate completar cada linha.
        with cliente.makefile("r", encoding="utf-8", errors="replace") as respostas:
            msg = montar_login(usuario, senha)
            print(f"Enviando (texto claro): {msg!r}")
            cliente.sendall(msg)

            resposta = respostas.readline()
            print(f"Resposta do servidor: {resposta.strip()}")

            cliente.sendall(montar_quit())
            bye = respostas.readline()
            print(f"Servidor: {bye.strip()}")


if __name__ == "__main__":
    main()
