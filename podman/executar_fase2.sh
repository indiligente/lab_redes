#!/usr/bin/env bash
# Inicia o servidor da Fase 2 e mostra como executar proxy e cliente.
set -euo pipefail
cd "$(dirname "$0")/.."

for nome in servidor-fase2 proxy-fase2 cliente-fase2 wireshark-fase2 captura-fase2; do
    if podman container exists "$nome"; then
        echo "O container '$nome' ja existe. Encerre a Fase 2 antes de recriar o laboratorio."
        exit 1
    fi
done
if podman network exists lab-net-fase2; then
    echo "A rede 'lab-net-fase2' ja existe. Encerre a Fase 2 antes de recriar o laboratorio."
    exit 1
fi

podman build -t lab-servico -f podman/Containerfile.servico .
podman build -t lab-proxy -f podman/Containerfile.proxy .
podman network create --internal --subnet 192.168.201.0/24 lab-net-fase2
podman run -d --name servidor-fase2 \
    --network lab-net-fase2 --ip 192.168.201.11 \
    lab-servico python3 -u servidor.py 0.0.0.0 9999

cat <<'INSTRUCOES'

Servidor iniciado. Confira: podman logs servidor-fase2

Em outro terminal, inicie o proxy interativo:
podman run -it --rm --name proxy-fase2 --network lab-net-fase2 --ip 192.168.201.12 -p 127.0.0.1:3001:3001 lab-proxy python3 -u proxy.py 0.0.0.0 8888 192.168.201.11 9999 --alterar

Antes dos clientes, inicie o Wireshark web:
bash podman/wireshark_fase2.sh

Abra https://localhost:3001, escolha eth0 e inicie a captura.
Ou capture sem interface grafica:
bash podman/captura_fase2.sh iniciar

Depois que a captura estiver ativa, inicie o cliente:
podman run -it --rm --name cliente-fase2 --network lab-net-fase2 lab-servico python3 cliente.py 192.168.201.12 8888

Para executar sem alterar mensagens, omita --alterar no proxy.
Para fixar as credenciais, acrescente --usuario Goku --senha testeteste.
No Wireshark, clique em Parar para encerrar a captura e analisar os fluxos.
Se iniciou pelo terminal, finalize e salve com: bash podman/captura_fase2.sh parar
INSTRUCOES
