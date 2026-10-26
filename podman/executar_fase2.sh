#!/usr/bin/env bash
# Inicia o servidor da Fase 2 e mostra como executar proxy e cliente.
set -euo pipefail
cd "$(dirname "$0")/.."

for nome in servidor-fase2 proxy-fase2 cliente-fase2; do
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
podman run -it --rm --name proxy-fase2 --network lab-net-fase2 --ip 192.168.201.12 lab-proxy python3 -u proxy.py 0.0.0.0 8888 192.168.201.11 9999 --alterar

Depois, em outro terminal, inicie o cliente:
podman run -it --rm --name cliente-fase2 --network lab-net-fase2 lab-servico python3 cliente.py 192.168.201.12 8888

Para executar sem alterar mensagens, omita --alterar no proxy.
Para fixar as credenciais, acrescente --usuario Goku --senha testeteste.
INSTRUCOES
