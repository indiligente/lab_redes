# Fase 1 — Reconhecimento e Escuta Passiva

Laboratório de Redes de Computadores — Interceptação e Defesa de um Protocolo de Aplicação
**Grupo:** Carlos Eduardo Alves Pereira Cunha, Eduardo Carlesso Silveira

## 1. Topologia (Podman, substituindo as 3 VMs do enunciado)

A turma foi orientada a usar **Podman** em vez de VMs completas. A topologia de 3 nós (cliente/servidor/observador) virou 3 containers na mesma rede isolada `lab-net` (bridge Podman, sub-rede `192.168.200.0/24`):

| Nó | Papel | Container | IP |
|---|---|---|---|
| servidor | Servidor PLP | `servidor` | `192.168.200.11` (fixo) |
| cliente | Cliente PLP | `cliente` | dinâmico (atribuído pelo Podman a cada execução, container efêmero `--rm`) |
| observador | Sniffer passivo | `observador` | mesmo IP do servidor (compartilha namespace de rede) |

### Por que o observador compartilha a rede do servidor

Uma VM em modo "Rede Interna" do VirtualBox (cenário original do enunciado) se comporta como um **hub**: todos no segmento recebem os mesmos quadros, bastando modo promíscuo pra capturar tráfego alheio. A bridge do `podman network create`, por outro lado, é uma **bridge Linux real, que funciona como switch**: só entrega tráfego unicast ao destino certo. Um 4º container "na mesma rede" em modo promíscuo não veria o tráfego cliente↔servidor.

A solução adotada: o `observador` sobe com `--network container:servidor`, compartilhando o namespace de rede do `servidor` — assim ele enxerga diretamente tudo que entra e sai do servidor, suficiente para demonstrar a quebra de confidencialidade pedida na Fase 1.

## 2. Pré-requisitos

```bash
sudo apt install -y podman   # Ubuntu/Debian
# ou: sudo dnf install -y podman   # Fedora/RHEL
```

Não é necessário Docker. Todos os comandos abaixo assumem que você está na raiz do projeto (`fase1_lab_redes/`) e **sem `sudo`** (modo rootless padrão) — veja a Seção 7 se precisar do modo com `sudo`.

## 3. Como executar

### 3.1 Build + subir o servidor

```bash
bash podman/executar_podman.sh
```

Builda `lab-servico` e `lab-sniffer`, cria a rede `lab-net` e sobe o `servidor` em background.

### 3.2 Subir o observador (sniffer próprio, em outro terminal)

```bash
podman run -it --rm --name observador \
  --network container:servidor \
  --cap-add NET_RAW --cap-add NET_ADMIN \
  -v "$(pwd)/sniffer:/app:Z" -w /app \
  lab-sniffer python3 sniffer.py eth0 9999
```

Deixe esse terminal aberto — ele vai mostrando, pacote a pacote, o que o cliente envia.

### 3.3 Rodar o cliente (em um terceiro terminal)

```bash
podman run --rm --name cliente \
  --network lab-net \
  -v "$(pwd)/servico:/app:Z" -w /app \
  lab-servico python3 cliente.py 192.168.200.11 9999 Cadu senha123
```

Troque usuário/senha pra testar os três casos:
- **200 OK**: credenciais corretas (ex.: `Cadu senha123`).
- **401 UNAUTHORIZED**: usuário existe mas senha errada (ex.: `Cadu senhaErrada`).
- **400 BAD_REQUEST**: usuário com espaço dentro, entre aspas (ex.: `"usuario com espaco" senha123`) — quebra o formato `LOGIN <usuario> <senha>` por virar mais de 2 argumentos.

### 3.4 Encerrando e limpando

Inicialmente pare o sniffer com o ctrl+C. Desta forma, faça:

```bash
bash podman/limpar_podman.sh
```

Isso limpa o cliente e o servidor após o fechamento do sniffer.

(`limpar_podman.sh` já faz essa limpeza com `-t 0`, matando os containers na hora em vez de esperar o tempo de graça padrão de 10s, que trava o script já que `servidor.py`/`sniffer.py` não tratam `SIGTERM`.)


## 4. Problemas comuns e soluções

### 4.1 Wireshark captura pacotes

Rodar **tudo** com `sudo` (servidor, observador, cliente, Wireshark) — nesse modo (rootful) o Podman cria uma bridge real (`podman1` ou similar) visível no namespace principal, e o Wireshark pode capturar direto nela. **Não misture** comandos com e sem `sudo` no mesmo teste — servidor rootless e cliente rootful (ou vice-versa) ficam em redes completamente diferentes e nunca se enxergam.

### 4.3 `podman rm -f` ou `limpar_podman.sh` parecem travados por ~10 segundos

`servidor.py` e `sniffer.py` não tratam o sinal `SIGTERM` (só `Ctrl+C`/`SIGINT`), então o Podman espera o tempo de graça padrão (10s) antes de forçar com `SIGKILL`. Use `-t 0` para pular essa espera: `podman rm -f -t 0 <nome>`. O `limpar_podman.sh` do projeto já faz isso.

### 4.4 `Error: network name lab-net already used` / `Error: ... container name already in use`

Sobra de uma execução anterior que não foi limpa direito. Rode `bash podman/limpar_podman.sh` antes de `executar_podman.sh` de novo. Se um container específico continuar "preso" (aparece em `podman ps -a` mas não em `podman ps`), remova-o direto: `podman rm -f -t 0 <nome>`.
