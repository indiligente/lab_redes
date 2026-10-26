# PLP — Laboratório de Redes: Fases 1 e 2

Aplicação cliente-servidor intencionalmente insegura, sniffer passivo e proxy MITM. O uso de **Podman foi autorizado pelo professor**. Toda a comunicação de aplicação usa sockets diretamente, sem frameworks.

- **Fase 1:** capturar e ler credenciais em texto claro.
- **Fase 2:** encaminhar sessões concorrentes e alterar credenciais em trânsito.

O protocolo é o **PLP — PUCRS Login Protocol**, sobre TCP. Mensagens terminam em uma quebra de linha real, representada neste documento por `\n`.

## 1. Arquivos principais

| Arquivo | Responsabilidade |
|---|---|
| `servico/protocolo.py` | Mensagens, porta padrão e contas de teste. |
| `servico/servidor.py` | Servidor TCP, uma thread por cliente e validação das credenciais. |
| `servico/cliente.py` | Envia LOGIN e QUIT; lê respostas completas por linha. |
| `sniffer/sniffer.py` | Captura passiva com socket raw e decodificação Ethernet/IPv4/TCP. |
| `proxy/proxy.py` | Proxy TCP concorrente, com alteração opcional de LOGIN. |
| `podman/executar_podman.sh` / `limpar_podman.sh` | Montagem e limpeza da Fase 1. |
| `podman/executar_fase2.sh` / `limpar_fase2.sh` | Montagem e limpeza da Fase 2. |
| `podman/wireshark_fase2.sh` | Inicia o container do Wireshark web em https://localhost:3001. |
| `podman/captura_fase2.sh` | Inicia e encerra uma captura no terminal, salvando em PCAPNG. |
| `tests/test_proxy.py` | Testes automatizados com sockets TCP reais locais. |

Documentação do projeto:

- [Relatório da Fase 1](docs/Relatorio%20T1%20Lab_Redes.md): demonstração da escuta passiva e imagens da captura.
- [Relatório da Fase 2](docs/Relatorio_Fase2.md): requisitos, concorrência, resultados e evidências do proxy.

Os comandos de execução e validação ficam neste README.

## 2. Pré-requisitos e protocolo

Use Linux e Podman. As imagens do serviço e do proxy usam Python 3.11 e não instalam bibliotecas externas. Para executar os testes diretamente no host, use Python 3.11 ou superior. Os atalhos de captura reutilizam a imagem do Wireshark, com ou sem interface gráfica; não é preciso instalar Wireshark/dumpcap no host. Wireshark/TShark não implementam o proxy; servem para observar e analisar o tráfego.

Execute os comandos na raiz do projeto. Os exemplos usam Podman **sem sudo**, em modo rootless. Caso escolha o modo com sudo, use-o em todos os comandos Podman da execução; os dois modos mantêm recursos separados.

| Usuário | Senha de teste |
|---|---|
| Cadu | senha123 |
| Goku | testeteste |
| Gohan | trabalhoLabRedes |

```text
LOGIN <usuario> <senha>\n  -> 200 OK <usuario>\n ou 401 UNAUTHORIZED\n
Comando/LOGIN malformado  -> 400 BAD_REQUEST\n
QUIT\n                   -> BYE\n
```

Não há TLS, autenticação do servidor ou proteção criptográfica de integridade. O servidor compara usuário/senha com um dicionário; ele não implementa operações protegidas após o login.

## 3. Topologias

As fases usam redes diferentes para poderem ser montadas e encerradas separadamente. Ambas são bridges criadas com `--internal`, restringindo acesso externo. Isso não representa isolamento absoluto do host. Apenas a interface web é publicada no host, em `127.0.0.1:3001`; as portas PLP 8888/9999 continuam internas.

| Fase | Rede | Servidor | Proxy | Cliente |
|---|---|---|---|---|
| 1 | `lab-net`, `192.168.200.0/24` | `servidor`, `.11:9999` | — | IP dinâmico, conecta ao servidor. |
| 2 | `lab-net-fase2`, `192.168.201.0/24` | `servidor-fase2`, `.11:9999` | `proxy-fase2`, `.12:8888` | IP dinâmico, conecta ao proxy. |

Na Fase 1, `observador` compartilha o namespace de rede de `servidor` para enxergar seus pacotes. Uma bridge funciona como switch: estar na mesma sub-rede não garante receber unicast de terceiros. A rede interna do VirtualBox também é um switch, com políticas próprias de captura promíscua; não é um hub.

Na Fase 2 o proxy tem endereço próprio. O redirecionamento é explícito, configurando o destino do cliente, como permitido no enunciado:

```text
cliente -- TCP para .12:8888 --> proxy -- outra conexão TCP --> .11:9999 servidor
cliente <-- resposta --------- proxy <-- resposta ------------------- servidor
```

O requisito 1 da Fase 2 diz: “O redirecionamento do tráfego para o proxy deve ser feito por configuração do próprio serviço, por exemplo, apontando o cliente ao proxy.” Portanto, ARP/DNS spoofing não é necessário para esta entrega.

## 4. Executar a Fase 1

### Terminal A: montar e conferir o servidor

```bash
bash podman/executar_podman.sh
podman logs servidor
podman network inspect lab-net
```

O campo `internal` deve ser `true`. Se houver recursos de uma execução anterior, encerre a Fase 1 com seu script de limpeza antes de remontar. O script não remove automaticamente uma rede preexistente.

### Terminal B: observador passivo

```bash
podman run -it --rm --name observador \
  --network container:servidor --cap-add NET_RAW \
  -v "$(pwd)/sniffer:/app:Z" -w /app \
  lab-sniffer python3 -u sniffer.py eth0 9999
```

### Terminal C: cliente direto

```bash
podman run --rm --name cliente --network lab-net \
  -v "$(pwd)/servico:/app:Z" -w /app \
  lab-servico python3 cliente.py 192.168.200.11 9999 Cadu senha123
```

Espere `200 OK Cadu` e `BYE`, com credenciais legíveis no observador. A senha `errada` produz 401; o usuário `"usuario com espaco"` produz 400. Para entrada interativa, use `-it` e omita usuário/senha.

Pare o observador com Ctrl+C e execute:

```bash
bash podman/limpar_podman.sh
```

## 5. Executar a Fase 2 no Podman

### Terminal A: montar e conferir o servidor

```bash
bash podman/executar_fase2.sh
podman logs servidor-fase2
podman network inspect lab-net-fase2
```

O script constrói `lab-servico` e `lab-proxy`, cria a rede interna e inicia o servidor. Ele imprime os comandos dos outros terminais; o proxy é iniciado separadamente para permitir entrada interativa. As imagens usam `COPY`: após editar o código, encerre e remonte a Fase 2 para reconstruí-las.

### Terminal B: proxy com alteração e entrada interativa

```bash
podman run -it --rm --name proxy-fase2 \
  --network lab-net-fase2 --ip 192.168.201.12 -p 127.0.0.1:3001:3001 \
  lab-proxy python3 -u proxy.py 0.0.0.0 8888 192.168.201.11 9999 --alterar
```

Informe `Goku` e `testeteste` como credenciais de substituição. As perguntas ocorrem uma única vez, antes de aceitar clientes.

Para executar com valores fixos e sem perguntas, acrescente `--usuario Goku --senha testeteste`. Para encaminhar sem alterar, omita `--alterar` e os parâmetros de credenciais. Pare o proxy anterior antes de iniciar outro com o mesmo nome/IP.

### Terminal C: iniciar a captura

Escolha uma das duas opções antes de executar os clientes.

**Com interface web:**

```bash
bash podman/wireshark_fase2.sh
```

Abra **https://localhost:3001** no navegador. Na primeira abertura, aceite manualmente o certificado local autoassinado. O primeiro uso baixa a imagem `lscr.io/linuxserver/wireshark`; os seguintes reutilizam o download.

O container `wireshark-fase2` compartilha a rede do proxy, permitindo observar cliente–proxy e proxy–servidor. A interface web é disponibilizada pela porta publicada no comando do proxy; por isso o parâmetro `-p 127.0.0.1:3001:3001` deve estar presente. HTTPS protege a interface gráfica, não o PLP, que continua em texto claro.

Na tela inicial do Wireshark, preencha o filtro de captura com `tcp port 8888 or tcp port 9999` e dê dois cliques em **eth0**. Execute os clientes somente depois de a captura começar. Não são necessárias permissões de captura no host: elas são concedidas ao container apenas para a rede do laboratório.

**Sem interface gráfica:**

```bash
bash podman/captura_fase2.sh iniciar
```

Quando aparecer **Captura ativa**, execute os clientes. O comando retorna ao terminal e a gravação continua em segundo plano. Ele inicia somente o `dumpcap`, ferramenta de captura do Wireshark, em `captura-fase2`, compartilhando a rede do proxy. Não precisa iniciar `wireshark-fase2`, abrir o navegador nem publicar a porta 3001 para essa opção. Captura `eth0`, nas portas 8888 e 9999.

O arquivo recebe um nome com data/hora em `docs/evidencias/capturas/`. Para escolher o nome, use `bash podman/captura_fase2.sh iniciar minha-captura.pcapng`. Um arquivo existente nunca é sobrescrito.

### Terminal D: cliente interativo apontando para o proxy

```bash
podman run -it --rm --name cliente-fase2 --network lab-net-fase2 \
  lab-servico python3 cliente.py 192.168.201.12 8888
```

Digite `Cadu` e `senha123`. Com alteração ativa, o servidor recebe Goku e o cliente exibe `200 OK Goku`. O proxy mostra a mensagem original e a modificada. Sem alteração, o resultado é `200 OK Cadu`.

Para uma execução automática:

```bash
podman run --rm --network lab-net-fase2 \
  lab-servico python3 cliente.py 192.168.201.12 8888 Cadu senha123
```

Omitir `--name` permite iniciar vários containers de cliente simultaneamente sem conflito de nomes.

### Parar e analisar a captura

Se iniciou **pelo terminal**, finalize com:

```bash
bash podman/captura_fase2.sh parar
```

O comando espera a gravação terminar, remove somente o container de captura e informa o caminho do arquivo salvo. O laboratório continua ativo. Os pacotes são gravados durante a coleta; `parar` fecha o arquivo corretamente. Para analisar na interface web depois, inicie `wireshark_fase2.sh` e use **Arquivo → Abrir**, escolhendo o arquivo em `/captures`. Também pode abri-lo no Wireshark instalado no host.

Se iniciou **pela interface web**:

1. No Wireshark, observe os pacotes chegando enquanto executa os clientes.
2. Clique no **quadrado vermelho — Parar**. O laboratório continua ativo, mas a captura é encerrada e os pacotes permanecem na janela para análise.
3. Mantenha o filtro `tcp.port == 8888 || tcp.port == 9999`. Em **Estatísticas → Conversações → TCP**, confira as conexões. Cada sessão PLP usa duas conexões TCP.
4. Selecione um LOGIN destinado à porta 8888 e use **Seguir → Fluxo TCP**, com exibição ASCII. Essa conversa mostra o LOGIN original e a resposta recebida pelo cliente.
5. Faça o mesmo com o LOGIN destinado à porta 9999. Essa conversa mostra a mensagem entregue ao servidor, já modificada quando `--alterar` está ativo.
6. Use **Arquivo → Salvar como** e escolha um arquivo em **`/captures`**, por exemplo `/captures/minha-captura.pcapng`. Essa pasta corresponde a `docs/evidencias/capturas/` no host. Os números dos pacotes/fluxos mudam entre execuções.

Para comparar com o modo normal, finalize e salve a captura. Se estiver usando o container gráfico, remova-o com `podman rm -f -t 0 wireshark-fase2`. Encerre o proxy e reinicie-o sem as opções de alteração. Inicie outra captura pela opção escolhida. Os arquivos salvos permanecem no host.

### Comportamentos da alteração e da sessão

- `--alterar` substitui as credenciais de todo LOGIN com três campos não vazios, separados por espaço; o comando é comparado sem distinguir maiúsculas/minúsculas. LOGIN malformado e outros comandos seguem ao servidor.
- A substituição também pode transformar uma tentativa com senha original incorreta em um login aceito se a conta configurada no proxy for válida. Uma senha de substituição incorreta continua recebendo 401.
- Usuário/senha podem ser fornecidos por parâmetros, digitados ou combinados; os valores de substituição não podem ser vazios ou conter espaços/quebras de linha.
- Cada sessão possui thread, sockets e buffers próprios. A configuração compartilhada é imutável. Um `Lock` protege apenas a escrita dos logs.
- Timeout: 60 segundos de espera por operação de rede. Limite: 4.096 bytes por linha, incluindo `\n`.
- Linhas vazias recebem 400 no proxy. Linhas grandes demais ou encerradas incompletas fecham só a sessão afetada. Falhas de rede são registradas e isoladas por sessão.
- O fluxo segue uma requisição e uma resposta por vez, adequado ao PLP. O proxy não implementa um relay genérico para protocolos com mensagens espontâneas do servidor.

### Encerrar a Fase 2

Se usou a interface gráfica, salve o arquivo antes. Para encerrar o laboratório, execute:

```bash
bash podman/limpar_fase2.sh
```

A limpeza finaliza a captura do terminal antes de remover os demais containers nomeados da Fase 2 e sua rede. As capturas no host e o volume `wireshark-fase2-config`, com as configurações da interface, são preservados. Se capturou pela interface gráfica, salve o arquivo antes da limpeza. Clientes adicionais com nomes automáticos devem ter terminado; remova os que ainda estiverem ativos antes de remover a rede. Os demais containers são encerrados imediatamente com `-t 0`.

## 6. Testes e evidências

### Testes automatizados locais

```bash
python3 -B -m unittest discover -s tests -v
```

São 25 testes com TCP real restrito a `127.0.0.1`, processos temporários e biblioteca padrão. Cobrem 200/401/400, oito sessões simultâneas, cliente com linha pendente, fragmentação/agrupamento, malformação, limites, desconexões, resets, timeouts, indisponibilidade/recuperação do servidor, alteração, parâmetros e entrada interativa. Os timeouts são reduzidos apenas nos processos de teste.

### Evidências já produzidas no Podman

Os arquivos estão em [docs/evidencias/fase2](docs/evidencias/fase2/):

- `fase2-normal.pcap` e `fase2-alteracao.pcap`: tráfego real, abrível no Wireshark.
- `pacotes-normal.tsv` e `pacotes-alteracao.tsv`: números, fluxos, endereços e payloads extraídos pelo TShark.
- Logs de cliente, proxy e servidor; resultado da validação; configuração da rede e hashes dos arquivos usados.

As duas capturas PCAP foram feitas por um socket raw auxiliar compartilhando a rede do proxy e decodificadas pelo **TShark**, ferramenta do Wireshark. A coleta não modifica o tráfego. A integração gráfica também foi validada, como registrado abaixo e no relatório.

Na captura de alteração, os quadros **7, 14, 16 e 18** mostram, respectivamente, LOGIN de Cadu chegando ao proxy, LOGIN de Goku saindo, aceitação pelo servidor e resposta ao cliente. Esses números pertencem à captura fornecida; novas execuções terão outros números.

### Conferir no Wireshark

Abra `fase2-alteracao.pcap`, aplique `tcp.port == 8888 || tcp.port == 9999` e examine os quadros indicados. Use **Seguir → Fluxo TCP** em ASCII. Existem dois fluxos: cliente–proxy e proxy–servidor; compare ambos para ver a troca. Um único fluxo não contém os dois lados do intermediário.

Para conferir pelo terminal:

```bash
tshark -r docs/evidencias/fase2/fase2-alteracao.pcap \
  -Y 'tcp.len > 0 && (tcp.port == 8888 || tcp.port == 9999)' \
  -T fields -e frame.number -e ip.src -e tcp.srcport -e ip.dst -e tcp.dstport -e tcp.payload
```

### Onde a captura começa

`executar_fase2.sh` inicia o servidor e mostra os comandos dos outros terminais. Na opção web, `wireshark_fase2.sh` inicia a interface; a captura começa quando você seleciona **eth0** e clica em iniciar. O quadrado vermelho encerra a coleta. Não há início automático ao abrir a URL. Na opção terminal, `captura_fase2.sh iniciar` começa a gravação diretamente, e `captura_fase2.sh parar` a encerra e confirma o arquivo salvo.

A imagem gráfica roda em modo X11 para compatibilidade com o navegador. O volume de configuração mantém as preferências da aplicação; a pasta `/captures` mantém os arquivos no projeto. Cliente, servidor e proxy continuam sendo os scripts Python próprios.

A integração web foi validada nesta execução: HTTPS 200 apenas em loopback; namespace compartilhado; três clientes com respostas 200/200/400; PCAPNG persistido e legível no host. Também foi realizada uma captura pela própria janela web, iniciada, parada e salva manualmente pelos controles do Wireshark; seus oito segmentos com dados confirmam o LOGIN original, o modificado e a resposta.

Referência da imagem: [Wireshark — LinuxServer.io](https://docs.linuxserver.io/images/docker-wireshark/).

## 7. Limites e solução de problemas

| Situação | Verificação |
|---|---|
| Nome de container/rede já existe | Use a limpeza da fase correspondente; os scripts não apagam recursos preexistentes na montagem. |
| Cliente não conecta | Confira logs, endereço do destino, porta, rede e uso consistente de sudo. Na Fase 2 o destino é `.12:8888`. |
| Proxy não aceita clientes após `--alterar` | Forneça as credenciais pedidas ou use os dois parâmetros; ele só escuta depois da configuração. |
| Wireshark não vê o tráfego | Use o container web após iniciar o proxy e capture em `eth0` com o filtro das duas portas. |
| URL não abre | Confira `podman logs wireshark-fase2` e a publicação `127.0.0.1:3001` no proxy. Use HTTPS. |
| Código editado não aparece na Fase 2 | Reconstrua as imagens e recrie os containers. |
| Captura mostra apenas LOGIN já alterado | A captura foi feita do lado do servidor; observe também o lado cliente–proxy. |

O sniffer da Fase 1 não remonta fluxos TCP e pode deixar de destacar credenciais divididas entre segmentos. O proxy lê linhas de sockets TCP normais, nos quais o kernel já ordena/remonta segmentos. Isso não corrige o sniffer.

A demonstração comprova adulteração de mensagem aceita e ausência de autenticação do servidor no cliente. Não comprova descobrir senhas desconhecidas, dispensar a verificação de senha ou acessar um recurso protegido. O cliente exibe a resposta e não verifica se o usuário retornado é o que solicitou. Threads não têm limite global e o timeout é de espera por operação, não uma duração máxima da sessão.
