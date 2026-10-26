#!/usr/bin/env bash
# Captura as duas conexoes do proxy sem abrir a interface grafica.
set -euo pipefail
cd "$(dirname "$0")/.."

PASTA="$(pwd)/docs/evidencias/capturas"
IMAGEM="lscr.io/linuxserver/wireshark:latest"

case "${1:-}" in
    iniciar)
        if (( $# > 2 )); then
            echo "Uso: bash podman/captura_fase2.sh iniciar [nome.pcapng]" >&2
            exit 1
        fi
        if [[ $(podman inspect proxy-fase2 --format '{{.State.Running}}' 2>/dev/null || true) != true ]]; then
            echo "Inicie o proxy-fase2 antes da captura, conforme o README." >&2
            exit 1
        fi
        if podman container exists captura-fase2; then
            echo "Ja existe uma captura. Finalize com: bash podman/captura_fase2.sh parar" >&2
            exit 1
        fi
        ARQUIVO="${2:-fase2-$(date +%Y%m%d-%H%M%S).pcapng}"
        if [[ ! "$ARQUIVO" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*\.pcapng$ ]]; then
            echo "Use um nome simples terminado em .pcapng, sem pastas ou espacos." >&2
            exit 1
        fi
        mkdir -p "$PASTA"
        if [[ -e "$PASTA/$ARQUIVO" ]]; then
            echo "O arquivo ja existe; escolha outro nome: $PASTA/$ARQUIVO" >&2
            exit 1
        fi
        podman run -d --name captura-fase2 \
            --network container:proxy-fase2 \
            --cap-add NET_ADMIN --cap-add NET_RAW --user 0 \
            --entrypoint /usr/bin/dumpcap \
            --label "lab.captura.arquivo=$ARQUIVO" \
            -v "$PASTA:/captures:z" \
            "$IMAGEM" -q -i eth0 -f 'tcp port 8888 or tcp port 9999' \
            -w "/captures/$ARQUIVO" >/dev/null

        # Aguarda o arquivo abrir antes de liberar a execucao dos clientes.
        for ((tentativa = 0; tentativa < 50; tentativa++)); do
            if [[ $(podman inspect captura-fase2 --format '{{.State.Running}}') != true ]]; then
                break
            fi
            if [[ -s "$PASTA/$ARQUIVO" ]]; then
                echo "Captura ativa. Execute os clientes agora."
                echo "Arquivo: $PASTA/$ARQUIVO"
                echo "Para finalizar: bash podman/captura_fase2.sh parar"
                exit 0
            fi
            sleep 0.1
        done
        podman logs captura-fase2 >&2
        echo "Nao foi possivel confirmar a captura. Execute o comando parar antes de tentar novamente." >&2
        exit 1
        ;;
    parar)
        if (( $# != 1 )); then
            echo "Uso: bash podman/captura_fase2.sh parar" >&2
            exit 1
        fi
        if ! podman container exists captura-fase2; then
            echo "Nenhuma captura pelo terminal esta ativa."
            exit 0
        fi
        ARQUIVO=$(podman inspect captura-fase2 --format '{{index .Config.Labels "lab.captura.arquivo"}}')
        if [[ $(podman inspect captura-fase2 --format '{{.State.Running}}') == true ]]; then
            # SIGINT equivale a Ctrl+C: fecha o arquivo antes de remover o container.
            podman kill --signal INT captura-fase2 >/dev/null
        fi
        CODIGO=$(podman wait captura-fase2)
        if [[ "$CODIGO" != 0 ]]; then
            podman logs captura-fase2 >&2
        fi
        podman rm captura-fase2 >/dev/null
        if [[ "$CODIGO" != 0 ]]; then
            echo "A captura terminou com erro ($CODIGO). Confira o arquivo: $PASTA/$ARQUIVO" >&2
            exit 1
        fi
        echo "Captura finalizada e salva: $PASTA/$ARQUIVO"
        ;;
    *)
        echo "Uso: bash podman/captura_fase2.sh iniciar [nome.pcapng] | parar" >&2
        exit 1
        ;;
esac
