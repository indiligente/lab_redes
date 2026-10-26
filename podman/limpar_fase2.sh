#!/usr/bin/env bash
# Remove apenas os containers e a rede da Fase 2.
set -euo pipefail

for nome in cliente-fase2 proxy-fase2 servidor-fase2; do
    if podman container exists "$nome"; then
        podman rm -f -t 0 "$nome"
    fi
done
if podman network exists lab-net-fase2; then
    podman network rm lab-net-fase2
fi
