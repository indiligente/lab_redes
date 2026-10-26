#!/usr/bin/env bash
# limpar_podman.sh
# Para e remove os containers e a rede criados pelo laboratorio.
set -euo pipefail

for c in cliente observador servidor; do
    if podman container exists "$c"; then
        podman rm -f -t 0 "$c"
    fi
done

if podman network exists lab-net; then
    podman network rm lab-net
fi

echo "Limpeza concluida."
