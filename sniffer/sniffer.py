#!/usr/bin/env python3
"""
sniffer.py
-----------
Interceptador PASSIVO (sniffer de aplicacao) para a Fase 1.

Roda na VM-observador. Usa um RAW SOCKET (AF_PACKET / SOCK_RAW) para
capturar quadros Ethernet brutos na interface de rede indicada,
decodifica manualmente os cabecalhos Ethernet -> IP -> TCP, filtra
o trafego da porta do protocolo PLP e extrai o conteudo em texto
claro (incluindo usuario/senha quando presentes), demonstrando a
quebra de confidencialidade do protocolo.

Este script NAO altera nem injeta trafego - e estritamente passivo
(somente leitura), rodando dentro do laboratorio isolado do grupo.

Requisitos:
    - Linux (usa socket.AF_PACKET, especifico do Linux).
    - Executar como root (raw sockets exigem privilegio elevado):
          sudo python3 sniffer.py <interface> [porta]

Exemplo (na VM-observador, interface eth1, porta padrao 9999):
    sudo python3 sniffer.py eth1 9999
"""

import socket
import struct
import sys
import time

PORTA_PADRAO = 9999


def mac_para_str(mac_bytes: bytes) -> str:
    return ":".join(f"{b:02x}" for b in mac_bytes)


def decodificar_ethernet(quadro: bytes):
    """Retorna (mac_origem, mac_destino, ethertype, payload)."""
    dest, orig, ethertype = struct.unpack("!6s6sH", quadro[:14])
    return mac_para_str(orig), mac_para_str(dest), ethertype, quadro[14:]


def decodificar_ip(pacote: bytes):
    """Retorna (ip_origem, ip_destino, protocolo, tamanho_header, payload)."""
    primeiro_byte = pacote[0]
    ihl = (primeiro_byte & 0x0F) * 4  # tamanho do cabecalho IP em bytes
    protocolo = pacote[9]
    ip_origem = socket.inet_ntoa(pacote[12:16])
    ip_destino = socket.inet_ntoa(pacote[16:20])
    return ip_origem, ip_destino, protocolo, ihl, pacote[ihl:]


def decodificar_tcp(segmento: bytes):
    """Retorna (porta_origem, porta_destino, tamanho_header, payload)."""
    porta_origem, porta_destino, seq, ack, offset_flags = struct.unpack(
        "!HHIIH", segmento[:14]
    )
    tamanho_header = ((offset_flags >> 12) & 0x0F) * 4
    return porta_origem, porta_destino, tamanho_header, segmento[tamanho_header:]


def extrair_credenciais(payload_texto: str):
    """
    Procura por uma linha 'LOGIN <usuario> <senha>' no payload de
    aplicacao capturado e retorna (usuario, senha) ou None.
    """
    for linha in payload_texto.splitlines():
        partes = linha.strip().split(" ")
        if len(partes) == 3 and partes[0].upper() == "LOGIN":
            return partes[1], partes[2]
    return None


def main():
    if len(sys.argv) < 2:
        print(f"Uso: sudo python3 {sys.argv[0]} <interface> [porta]")
        sys.exit(1)

    interface = sys.argv[1]
    porta_alvo = int(sys.argv[2]) if len(sys.argv) > 2 else PORTA_PADRAO

    ETH_P_ALL = 0x0003
    ETH_P_IP = 0x0800
    PROTO_TCP = 6

    try:
        raw = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
    except PermissionError:
        print("ERRO: este script precisa rodar como root (sudo). Raw sockets exigem privilegio.")
        sys.exit(1)
    except AttributeError:
        print("ERRO: socket.AF_PACKET so existe em Linux. Rode este sniffer na VM-observador Linux.")
        sys.exit(1)

    raw.bind((interface, 0))

    print(f"[sniffer] Capturando na interface '{interface}', filtrando TCP porta {porta_alvo}")
    print("[sniffer] Pressione Ctrl+C para parar.\n")

    numero_pacote = 0

    try:
        while True:
            quadro, _ = raw.recvfrom(65535)
            numero_pacote += 1

            mac_orig, mac_dest, ethertype, payload_eth = decodificar_ethernet(quadro)
            if ethertype != ETH_P_IP:
                continue  # so nos interessa IPv4 aqui

            ip_orig, ip_dest, protocolo, _, payload_ip = decodificar_ip(payload_eth)
            if protocolo != PROTO_TCP:
                continue  # so nos interessa TCP aqui

            porta_orig, porta_dest, _, payload_tcp = decodificar_tcp(payload_ip)
            if porta_orig != porta_alvo and porta_dest != porta_alvo:
                continue  # nao e trafego do protocolo PLP

            if not payload_tcp:
                continue  # pacote so de controle (SYN/ACK/FIN), sem dados de aplicacao

            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            texto = payload_tcp.decode("utf-8", errors="replace")

            print(f"--- pacote #{numero_pacote} [{ts}] ---")
            print(f"  {ip_orig}:{porta_orig} -> {ip_dest}:{porta_dest}")
            print(f"  payload bruto (texto claro): {texto!r}")

            credenciais = extrair_credenciais(texto)
            if credenciais:
                usuario, senha = credenciais
                print(f"  >>> CREDENCIAIS INTERCEPTADAS: usuario={usuario!r} senha={senha!r}")
            print()

    except KeyboardInterrupt:
        print(f"\n[sniffer] Encerrado. Total de pacotes TCP:{porta_alvo} capturados: {numero_pacote}")


if __name__ == "__main__":
    main()
