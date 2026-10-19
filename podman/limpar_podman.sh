#!/usr/bin/env bash
# limpar_podman.sh
# Para e remove os containers e a rede criados pelo laboratorio.
set -uo pipefail

for c in cliente observador servidor; do
    podman rm -f "$c" >/dev/null 2>&1 && echo "Container '$c' removido." || true
done

podman network rm -f lab-net >/dev/null 2>&1 && echo "Rede 'lab-net' removida." || true

echo "Limpeza concluida."
