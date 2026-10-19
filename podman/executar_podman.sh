#!/usr/bin/env bash
# executar_podman.sh
# ---------------------------------------------------------------
# Monta o laboratorio da Fase 1 inteiramente com Podman, substituindo
# as 3 VMs (cliente/servidor/observador) por 3 containers na mesma
# rede isolada. Rode este script a partir da raiz do projeto
# (fase1_lab_redes/), ou seja: bash podman/executar_podman.sh
#
# Requisitos: podman instalado (sudo apt install podman  /  sudo dnf install podman)
# ---------------------------------------------------------------
set -euo pipefail

REDE="lab-net"
SUBNET="192.168.200.0/24"
IP_SERVIDOR="192.168.200.11"
IP_CLIENTE="192.168.200.10"
PORTA=9999

echo "== 1) Build das imagens =="
podman build -t lab-servico -f podman/Containerfile.servico .
podman build -t lab-sniffer -f podman/Containerfile.sniffer .

echo "== 2) Criando rede isolada (${REDE}, ${SUBNET}) =="
podman network exists "${REDE}" && podman network rm -f "${REDE}" >/dev/null 2>&1 || true
podman network create "${REDE}" --subnet "${SUBNET}"

echo "== 3) Subindo o servidor (IP fixo ${IP_SERVIDOR}) =="
podman run -d --name servidor \
    --network "${REDE}" --ip "${IP_SERVIDOR}" \
    -v "$(pwd)/servico:/app:Z" -w /app \
    lab-servico python3 servidor.py 0.0.0.0 "${PORTA}"

sleep 1

echo "== 4) Subindo o observador (sniffer passivo) =="
echo "   Metodo: compartilhando o namespace de rede do servidor"
echo "   (--network container:servidor), pois a bridge do Podman"
echo "   funciona como switch e nao replica trafego unicast para"
echo "   um 4o container como faria uma rede 'Interna' do VirtualBox."
echo "   Isso ainda demonstra plenamente a quebra de confidencialidade:"
echo "   o observador enxerga tudo que entra/sai do servidor."
echo
echo "   Em outro terminal, rode:"
echo
echo "     podman run -it --rm --name observador \\"
echo "       --network container:servidor \\"
echo "       --cap-add NET_RAW --cap-add NET_ADMIN \\"
echo "       -v \"\$(pwd)/sniffer:/app:Z\" -w /app \\"
echo "       lab-sniffer python3 sniffer.py eth0 ${PORTA}"
echo
echo "== 5) Depois, em outro terminal, rode o cliente =="
echo
echo "     podman run --rm --name cliente \\"
echo "       --network ${REDE} \\"
echo "       -v \"\$(pwd)/servico:/app:Z\" -w /app \\"
echo "       lab-servico python3 cliente.py ${IP_SERVIDOR} ${PORTA} Cadu senha123"
echo
echo "== Pronto. Servidor rodando em background (podman logs -f servidor para ver o log). =="
