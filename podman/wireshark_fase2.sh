#!/usr/bin/env bash
# Inicia o Wireshark web na mesma rede do proxy.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ $(podman inspect proxy-fase2 --format '{{.State.Running}}' 2>/dev/null || true) != true ]]; then
    echo "Inicie o proxy-fase2 antes do Wireshark, conforme o README." >&2
    exit 1
fi
if ! podman port proxy-fase2 3001/tcp 2>/dev/null | grep -qx '127.0.0.1:3001'; then
    echo "Recrie o proxy com: -p 127.0.0.1:3001:3001 (veja o README)." >&2
    exit 1
fi
if podman container exists wireshark-fase2; then
    REDE_ESPERADA="container:$(podman inspect proxy-fase2 --format '{{.Id}}')"
    if [[ $(podman inspect wireshark-fase2 --format '{{.HostConfig.NetworkMode}}') != "$REDE_ESPERADA" ]]; then
        echo "O proxy foi recriado. Remova wireshark-fase2 e execute este atalho novamente." >&2
        exit 1
    fi
    if [[ $(podman inspect wireshark-fase2 --format '{{.State.Running}}') != true ]]; then
        podman start wireshark-fase2 >/dev/null
    fi
    echo "O Wireshark ja foi criado. Acesse https://localhost:3001 ou remova-o antes de recriar."
    exit 0
fi

mkdir -p docs/evidencias/capturas
podman run -d --name wireshark-fase2 \
    --network container:proxy-fase2 \
    --cap-add NET_ADMIN --cap-add NET_RAW --shm-size=1g \
    -e PUID=0 -e PGID=0 -e TZ=America/Sao_Paulo -e PIXELFLUX_WAYLAND=false \
    -v wireshark-fase2-config:/config \
    -v "$(pwd)/docs/evidencias/capturas:/captures:z" \
    lscr.io/linuxserver/wireshark:latest

echo "Wireshark iniciando: https://localhost:3001"
echo "Na primeira abertura, aceite o certificado local autoassinado."
echo "Capture eth0 com filtro: tcp port 8888 or tcp port 9999"
echo "Salve em /captures para manter os arquivos na pasta docs/evidencias/capturas."
