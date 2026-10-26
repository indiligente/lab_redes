#!/usr/bin/env python3
"""Proxy PLP concorrente com credenciais de substituicao configuraveis.

Uso:
    python3 proxy.py <host_proxy> <porta_proxy> <host_servidor> <porta_servidor>
                    [--alterar [--usuario USUARIO] [--senha SENHA]]

Cada cliente e atendido por uma thread, com conexoes e buffers proprios.
"""

import argparse
import socket
import threading


TIMEOUT = 60
MAX_LINHA = 4096
LOCK_LOG = threading.Lock()


def log(sessao: str, mensagem: str):
    # Apenas a saida do terminal e compartilhada entre as threads.
    with LOCK_LOG:
        print(f"[{sessao}] {mensagem}", flush=True)


def ler_linha(entrada):
    linha = entrada.readline(MAX_LINHA + 1)
    if len(linha) > MAX_LINHA:
        raise ValueError(f"Linha excede {MAX_LINHA} bytes")
    if linha and not linha.endswith(b"\n"):
        raise ValueError("Conexao encerrada com linha incompleta")
    return linha


def encaminhar(cliente: socket.socket, servidor: socket.socket, sessao: str,
               login_substituto: bytes | None = None):
    # Leitura binaria por linha preserva os bytes e aguarda a mensagem completa.
    with cliente.makefile("rb") as requisicoes, servidor.makefile("rb") as respostas:
        while True:
            requisicao = ler_linha(requisicoes)
            if not requisicao:
                return

            # O servidor ignora linhas vazias, sem gerar resposta.
            if not requisicao.strip():
                log(sessao, "Linha vazia rejeitada: 400 BAD_REQUEST")
                cliente.sendall(b"400 BAD_REQUEST\n")
                continue

            partes = requisicao.strip().split(b" ")
            if (login_substituto is not None and len(partes) == 3
                    and partes[0].upper() == b"LOGIN" and all(partes[1:])
                    and requisicao != login_substituto):
                original = requisicao
                requisicao = login_substituto
                log(sessao, f"ALTERACAO: original={original!r} modificada={requisicao!r}")

            log(sessao, f"cliente -> servidor: {requisicao!r}")
            servidor.sendall(requisicao)

            resposta = ler_linha(respostas)
            if not resposta:
                return

            log(sessao, f"servidor -> cliente: {resposta!r}")
            cliente.sendall(resposta)

            if resposta == b"BYE\n":
                return


def tratar_cliente(cliente: socket.socket, endereco, host_servidor: str, porta_servidor: int,
                   login_substituto: bytes | None = None):
    sessao = f"{endereco[0]}:{endereco[1]}"
    log(sessao, "Cliente conectado")
    with cliente:
        try:
            cliente.settimeout(TIMEOUT)
            with socket.create_connection((host_servidor, porta_servidor), timeout=TIMEOUT) as servidor:
                encaminhar(cliente, servidor, sessao, login_substituto)
        except socket.timeout:
            log(sessao, f"Timeout de {TIMEOUT}s; encerrando sessao")
        except (OSError, ValueError) as erro:
            log(sessao, f"Erro na sessao: {erro}")
        finally:
            log(sessao, "Sessao encerrada")


def main():
    parser = argparse.ArgumentParser(description="Proxy do protocolo PLP para o laboratorio.")
    parser.add_argument("host_proxy")
    parser.add_argument("porta_proxy", type=int)
    parser.add_argument("host_servidor")
    parser.add_argument("porta_servidor", type=int)
    parser.add_argument("--alterar", action="store_true",
                        help="Substitui as credenciais dos comandos LOGIN validos.")
    parser.add_argument("--usuario", help="Usuario de substituicao; perguntado se omitido.")
    parser.add_argument("--senha", help="Senha de substituicao; perguntada se omitida.")
    args = parser.parse_args()
    if not args.alterar and (args.usuario is not None or args.senha is not None):
        parser.error("--usuario e --senha exigem --alterar")

    login_substituto = None
    if args.alterar:
        # A entrada ocorre uma unica vez, antes de iniciar as threads.
        try:
            usuario = args.usuario if args.usuario is not None else input("Usuario de substituicao: ")
            senha = args.senha if args.senha is not None else input("Senha de substituicao: ")
        except (EOFError, KeyboardInterrupt):
            parser.error("Informe as credenciais no terminal ou use --usuario e --senha")
        if any(not campo or any(c.isspace() for c in campo) for campo in (usuario, senha)):
            parser.error("Usuario e senha devem ser preenchidos e nao podem conter espacos ou quebras de linha")
        login_substituto = f"LOGIN {usuario} {senha}\n".encode("utf-8")
        if len(login_substituto) > MAX_LINHA:
            parser.error(f"LOGIN de substituicao excede {MAX_LINHA} bytes")

    host_proxy, porta_proxy = args.host_proxy, args.porta_proxy
    host_servidor, porta_servidor = args.host_servidor, args.porta_servidor

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as proxy:
        proxy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        proxy.bind((host_proxy, porta_proxy))
        proxy.listen()
        log(
            "proxy",
            f"Proxy PLP em {host_proxy}:{porta_proxy} "
            f"-> servidor {host_servidor}:{porta_servidor}",
        )
        log("proxy", "Modo: alteracao de LOGIN" if args.alterar else "Modo: encaminhamento normal")

        try:
            while True:
                cliente, endereco = proxy.accept()
                threading.Thread(
                    target=tratar_cliente,
                    args=(cliente, endereco, host_servidor, porta_servidor, login_substituto),
                    daemon=True,
                ).start()
        except KeyboardInterrupt:
            log("proxy", "Encerrando proxy")


if __name__ == "__main__":
    main()
