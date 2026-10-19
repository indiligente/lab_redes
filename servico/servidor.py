#!/usr/bin/env python3
"""
servidor.py
------------
Servidor do protocolo PLP (PUCRS Login Protocol).

Roda na VM-servidor. Aceita conexoes TCP na porta definida em
protocolo.py (padrao 9999), le uma linha de comando (LOGIN ou QUIT)
e responde conforme o protocolo. Toda a comunicacao e feita em
TEXTO CLARO, de proposito, para a Fase 1 do trabalho.

Uso:
    python3 servidor.py [host] [porta]

Exemplo (na VM-servidor):
    python3 servidor.py 0.0.0.0 9999
"""

import socket
import sys
import threading
import time

from protocolo import HOST_PADRAO, PORTA_PADRAO, USUARIOS, interpretar_mensagem


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def tratar_cliente(conexao: socket.socket, endereco):
    ip_cliente, porta_cliente = endereco
    log(f"Nova conexao de {ip_cliente}:{porta_cliente}")

    buffer = ""
    try:
        with conexao:
            conexao.settimeout(60)
            while True:
                dados = conexao.recv(4096)
                if not dados:
                    log(f"Cliente {ip_cliente}:{porta_cliente} desconectou")
                    break

                buffer += dados.decode("utf-8", errors="replace")

                while "\n" in buffer:
                    linha, buffer = buffer.split("\n", 1)
                    if not linha:
                        continue

                    comando, args = interpretar_mensagem(linha)

                    if comando == "LOGIN":
                        if len(args) != 2:
                            resposta = "400 BAD_REQUEST\n"
                            log(f"  -> requisicao LOGIN malformada: {linha!r}")
                        else:
                            usuario, senha = args
                            # Log propositalmente "didatico": mostra que o
                            # servidor recebeu as credenciais em texto claro.
                            log(
                                f"  -> tentativa de LOGIN recebida: "
                                f"usuario={usuario!r} senha={senha!r}"
                            )
                            if USUARIOS.get(usuario) == senha:
                                resposta = f"200 OK {usuario}\n"
                                log(f"  -> autenticacao OK para {usuario!r}")
                            else:
                                resposta = "401 UNAUTHORIZED\n"
                                log(f"  -> autenticacao FALHOU para {usuario!r}")
                        conexao.sendall(resposta.encode("utf-8"))

                    elif comando == "QUIT":
                        conexao.sendall(b"BYE\n")
                        log(f"  -> cliente {ip_cliente}:{porta_cliente} pediu QUIT")
                        return

                    else:
                        conexao.sendall(b"400 BAD_REQUEST\n")
                        log(f"  -> comando desconhecido: {linha!r}")

    except socket.timeout:
        log(f"Timeout na conexao com {ip_cliente}:{porta_cliente}")
    except ConnectionResetError:
        log(f"Conexao resetada por {ip_cliente}:{porta_cliente}")


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else HOST_PADRAO
    porta = int(sys.argv[2]) if len(sys.argv) > 2 else PORTA_PADRAO

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind((host, porta))
        servidor.listen(5)
        log(f"Servidor PLP escutando em {host}:{porta}")
        log(f"Usuarios cadastrados (apenas para teste): {list(USUARIOS.keys())}")

        try:
            while True:
                conexao, endereco = servidor.accept()
                t = threading.Thread(
                    target=tratar_cliente, args=(conexao, endereco), daemon=True
                )
                t.start()
        except KeyboardInterrupt:
            log("Encerrando servidor (Ctrl+C).")


if __name__ == "__main__":
    main()
