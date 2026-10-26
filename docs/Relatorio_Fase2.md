# Relatório da Fase 2 — Interceptação ativa com proxy MITM

Validação realizada em 26/10/2026. Este relatório descreve o código atual e evidências de execução real. A topologia usa Podman, autorizado pelo professor.

## 1. Objetivo e resultado

Foi implementado um intermediário TCP capaz de ler o PLP, encaminhar mensagens nos dois sentidos e substituir credenciais de LOGIN antes de entregá-las ao servidor. O proxy atende várias sessões simultâneas e isola falhas de cada conexão.

O resultado principal foi: o cliente enviou `LOGIN Cadu senha123`, o proxy encaminhou `LOGIN Goku testeteste`, o servidor autenticou Goku e o cliente recebeu `200 OK Goku`. A troca está comprovada nos logs e em dois fluxos TCP de uma captura real.

O código é coerente com a proposta da Fase 2 para um protocolo de requisição/resposta como o PLP. A expressão “quebra de autenticação” deve ser interpretada com precisão: o cliente não autentica o servidor e aceita a resposta recebida pelo intermediário; o servidor não detecta a alteração do conteúdo. A validação de usuário/senha do servidor continua funcionando.

## 2. Conferência com o enunciado da Fase 2

| Requisito fornecido | Como foi atendido | Evidência |
|---|---|---|
| Proxy com sockets; conexão de entrada e outra com o servidor; relay nos dois sentidos | `socket`, `accept`, `create_connection`, leitura por linha e `sendall`. | `proxy/proxy.py`; captura mostra duas conexões por sessão. |
| Redirecionamento por configuração do serviço | Cliente conecta em `192.168.201.12:8888`, endereço do proxy. | README e comandos do laboratório. |
| Leitura e modificação controlada | `--alterar` troca as credenciais de LOGIN válidos pelas configuradas; logs registram original e modificado. | Captura de alteração, quadros 7 e 14; logs do proxy. |
| Concorrência | Uma thread por cliente, com sockets e buffers separados. | Teste com barreira para oito sessões locais; oito sessões simultâneas no Podman. |
| Lidar com desconexões e mensagens malformadas sem derrubar as demais sessões | Tratamento de timeout/erros por thread, limite de linha e rejeição de linha incompleta. | Testes de timeout, reset, linha grande, malformação e recuperação. |
| Demonstrar mensagem alterada aceita como legítima | O servidor recebe o LOGIN modificado, valida Goku e retorna 200, que o cliente exibe. | Captura, quadros 14/16/18; logs do servidor e cliente. |

As quatro entregas da Fase 2 estão representadas: código do proxy, README com execução/topologia/redirecionamento, explicação do modelo de concorrência/região crítica neste documento e no guia, e demonstração com evidências na pasta `docs/evidencias/fase2/`.

## 3. Topologia e execução

Rede `lab-net-fase2`, bridge interna `192.168.201.0/24`, sem portas publicadas no host.

| Papel | Container | Endereço |
|---|---|---|
| Cliente | `cliente-fase2` ou nome automático | IP dinâmico. |
| Proxy | `proxy-fase2` | `192.168.201.12:8888`. |
| Servidor | `servidor-fase2` | `192.168.201.11:9999`. |

O script `podman/executar_fase2.sh` constrói as imagens, cria a rede e inicia o servidor. Proxy e cliente são iniciados nos terminais seguintes para permitir entrada interativa. Também podem receber todos os parâmetros por linha de comando. A rede e os nomes são distintos da Fase 1.

O redirecionamento é explícito: o cliente escolhe o endereço do proxy. Essa forma é permitida pelo enunciado. Não há ARP spoofing, modificação de rotas ou ataque a máquinas externas. O proxy precisa apenas de sockets TCP normais, sem capacidade de captura raw.

A rede existente na validação foi inspecionada: `internal: true`. Também foi verificada a ausência de rota IPv4 padrão no container servidor. A opção restringe acesso externo, mas não constitui isolamento absoluto do host.

Os comandos completos estão no [README](../README.md).

## 4. Modelo de concorrência e regiões críticas

A thread principal executa `accept()` continuamente e inicia uma thread para cada cliente. O atendimento da sessão ocorre em `tratar_cliente()`; uma sessão lenta não ocupa o laço de aceitação.

Cada thread possui:

- Socket do cliente aceito e outro socket conectado ao servidor.
- Leitores com buffer próprios para os dois sentidos.
- Requisição, resposta e identificador de sessão locais.
- Tratamento local de timeout, erro de rede e erro de formato/tamanho da linha.

A mensagem de substituição é construída uma vez antes de iniciar o servidor do proxy. Ela é um objeto `bytes`, imutável e compartilhado somente para leitura. As threads não recebem comandos pelo terminal nem alteram essa configuração.

A região crítica é a escrita dos logs. `LOCK_LOG`, um `threading.Lock`, protege a chamada de `print` para que um registro não seja intercalado com outro. O lock não é mantido durante leitura, conexão ou envio; portanto, não transforma o encaminhamento em atendimento sequencial.

As threads são `daemon`: ao encerrar o processo do proxy, os atendimentos também terminam. Não há limite global configurado para a quantidade de threads. O projeto demonstra concorrência no laboratório; não foi dimensionado como serviço de produção.

## 5. O que exatamente é alterado

Com `--alterar`, o proxy divide a linha em campos separados por espaço, procura um comando LOGIN com três campos não vazios e substitui a linha pela mensagem previamente configurada. A comparação do comando não distingue maiúsculas de minúsculas. A troca ocorre depois de receber a linha inteira.

Usuário e senha de substituição podem vir de `--usuario`/`--senha` ou de perguntas feitas apenas na inicialização. Valores vazios, com whitespace ou que gerem uma linha acima de 4.096 bytes são rejeitados na configuração.

Comando malformado segue ao servidor para a resposta correspondente. Uma linha vazia recebe 400 no próprio proxy, porque o servidor original a ignora sem responder. As respostas do servidor não são falsificadas: são retransmitidas como recebidas.

Um LOGIN que já seja idêntico ao configurado não precisa ser modificado e não produz registro de alteração. A ausência de `--alterar` mantém o encaminhamento sem substituição das credenciais.

## 6. Demonstração com captura real

As capturas foram coletadas por um socket raw auxiliar no namespace do proxy e gravadas em PCAP. Depois foram abertas e decodificadas pelo TShark, ferramenta da suíte Wireshark. Isso permitiu registrar os dois lados do proxy. Não foi feita uma nova verificação pela interface gráfica do Wireshark; os PCAPs podem ser abertos nela para a apresentação.

### 6.1 Sem alteração

Arquivo: [fase2-normal.pcap](evidencias/fase2/fase2-normal.pcap).

| Quadro | Direção | Conteúdo |
|---|---|---|
| 7 | Cliente `.2:46836` → proxy `.12:8888` | `LOGIN Cadu senha123\n` |
| 14 | Proxy `.12:42614` → servidor `.11:9999` | `LOGIN Cadu senha123\n` |
| 16 | Servidor → proxy | `200 OK Cadu\n` |
| 18 | Proxy → cliente | `200 OK Cadu\n` |

A tentativa posterior com `senhaErrada` aparece nos quadros 42 e 47 e recebe 401 nos quadros 49 e 51. Os índices `tcp.stream` desse segundo atendimento são 2 e 3.

### 6.2 Com alteração para Goku/testeteste

Arquivo: [fase2-alteracao.pcap](evidencias/fase2/fase2-alteracao.pcap).

| Quadro | Fluxo TCP | Direção | Conteúdo |
|---|---|---|---|
| 7 | 0 | Cliente `.5:33150` → proxy `.12:8888` | `LOGIN Cadu senha123\n` |
| 14 | 1 | Proxy `.12:42640` → servidor `.11:9999` | `LOGIN Goku testeteste\n` |
| 16 | 1 | Servidor → proxy | `200 OK Goku\n` |
| 18 | 0 | Proxy → cliente | `200 OK Goku\n` |
| 20/21 | 0/1 | Cliente → proxy → servidor | `QUIT\n` |
| 22/24 | 1/0 | Servidor → proxy → cliente | `BYE\n` |

A tentativa com senha original errada também foi alterada: quadro 44 contém `LOGIN Cadu senhaErrada`, quadro 49 contém `LOGIN Goku testeteste`, e os quadros 51/53 mostram 200. O servidor aceitou outra conta com senha correta, não a senha errada originalmente enviada.

O arquivo normal contém 24 segmentos com dados das portas do laboratório; o de alteração contém 96, incluindo o teste concorrente e o cliente interativo. Os números se referem a estes arquivos, não a resultados fixos de novas execuções.

### 6.3 Como conferir

Abra o PCAP de alteração no Wireshark, filtre `tcp.port == 8888 || tcp.port == 9999` e examine os quadros indicados. Em **Seguir Fluxo TCP**, compare os fluxos 0 e 1: o primeiro mostra o conteúdo do cliente, e o segundo o conteúdo que chegou ao servidor. A prova está nos bytes diferentes e na resposta 200, não apenas no tamanho dos pacotes.

Os mesmos dados estão nas tabelas [pacotes-normal.tsv](evidencias/fase2/pacotes-normal.tsv) e [pacotes-alteracao.tsv](evidencias/fase2/pacotes-alteracao.tsv).

## 7. Testes realizados

A suíte `python3 -B -m unittest discover -s tests -v` executou **25 testes em 6,509 segundos, todos aprovados** nesta validação. Os testes usam TCP real local e processos temporários. O timeout é reduzido nos processos de teste para não esperar 60 segundos.

Foram cobertos: cliente real com 200/401/400; oito sessões simultâneas com barreira; cliente com linha pendente; linhas fragmentadas/agrupadas; comandos malformados e linhas vazias; linha grande; EOF incompleto; reset dos dois lados; timeout dos dois lados; resposta incompleta; servidor indisponível e recuperação; preservação de bytes; alteração aceita; alteração somente de LOGIN válido; alteração fragmentada e concorrente; independência dos modos; entrada interativa; parâmetros personalizados/combinados; senha de substituição errada; configurações inválidas.

Além disso, a execução em containers confirmou:

| Verificação Podman | Resultado |
|---|---|
| Construção das imagens e montagem pelo script | Aprovado. |
| Rede interna e ausência de rota IPv4 padrão no servidor | Aprovado. |
| Modo normal: 200, 401, 400 e BYE | Aprovado. |
| Modo de alteração: conta original substituída, 200 para Goku | Aprovado. |
| LOGIN malformado permanece 400 no modo de alteração | Aprovado. |
| Oito sessões simultâneas no mesmo container cliente, com portas distintas | Todas receberam 200 e BYE. |
| Cliente com entrada interativa via stdin no container | Aprovado. |
| Limpeza pelo script específico da Fase 2 | Aprovado; recursos da Fase 1 preservados. |
| Decodificação dos PCAPs e comparação dos dois lados do proxy | Aprovado com TShark. |

A concorrência foi comprovada por sessões simultâneas, não por oito containers obrigatoriamente distintos. O requisito pede múltiplas conexões/sessões; um cliente pode abrir várias conexões.

## 8. Limites e precisão das conclusões

- Há quebra de integridade: os bytes que chegam ao servidor são diferentes dos enviados pelo cliente, sem detecção criptográfica.
- O cliente não autentica o servidor. Aceita conectar ao intermediário configurado e exibe sua resposta sem verificar a identidade do par ou comparar o usuário retornado.
- A demonstração usa contas de teste conhecidas. Não descobre uma senha desconhecida nem elimina a comparação de senha no servidor.
- O serviço não implementa recurso protegido ou autorização após login. A evidência termina na resposta de autenticação.
- O proxy segue requisição/resposta do PLP; não é um relay universal para protocolos com envio espontâneo pelo servidor.
- O timeout é de espera por operação de rede, não um prazo total da sessão. Não existe limite global de threads.
- O sniffer da Fase 1 continua sem remontagem TCP e com limitações de validação de cabeçalhos. A captura da Fase 2 e o proxy não dependem da extração automática desse sniffer.
- Os scripts da Fase 2 usam imagens com COPY. Alterações de código exigem reconstrução e recriação dos containers.

Esses limites devem ser apresentados junto da demonstração, sem atribuir ao experimento resultados que ele não mede.

## 9. Arquivos de evidência

A pasta [evidencias/fase2](evidencias/fase2/) contém as capturas, tabelas de pacotes, logs do proxy nos dois modos, saídas dos clientes e do servidor, inspeção da rede e resultado dos testes de integração. A verificação de montagem/limpeza está registrada em `resultado_validacao.txt`. `manifesto.json` registra hashes SHA-256 dos arquivos de aplicação e de montagem utilizados.

O roteiro operacional atualizado está no [README](../README.md). A explicação das funções, decisões e respostas para apresentação está no [Guia do código](Guia_do_codigo.md).
