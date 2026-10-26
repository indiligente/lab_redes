# Guia para entender e explicar o código

Este guia acompanha as Fases 1 e 2 do PLP. O objetivo é que você consiga explicar o caminho de uma mensagem, apontar onde ela é alterada e justificar concorrência, buffers e tratamento de falhas.

## 1. A ideia que você deve saber explicar primeiro

Criamos um serviço de login propositalmente inseguro. O cliente envia usuário e senha em texto claro. Na Fase 1, um sniffer observa esses bytes. Na Fase 2, um proxy recebe a mensagem, pode trocar as credenciais e a encaminha ao servidor. O servidor não possui um mecanismo criptográfico para detectar essa alteração.

O proxy não fica “magicamente” no caminho: configuramos o cliente para conectar ao seu IP. Essa forma de redirecionamento está prevista no enunciado.

```mermaid
sequenceDiagram
    participant C as Cliente
    participant P as Proxy (.12:8888)
    participant S as Servidor (.11:9999)
    C->>P: LOGIN Cadu senha123
    Note over P: --alterar ativo; destino Goku/testeteste
    P->>S: LOGIN Goku testeteste
    S-->>P: 200 OK Goku
    P-->>C: 200 OK Goku
    C->>P: QUIT
    P->>S: QUIT
    S-->>P: BYE
    P-->>C: BYE
```

Existem **duas conexões TCP**. O proxy atua como servidor para o cliente e como cliente para o servidor verdadeiro.

## 2. Vocabulário ligado ao nosso código

| Termo | Significado neste projeto |
|---|---|
| Socket | Objeto pelo qual o processo envia/recebe dados de rede. |
| IP e porta | Identificam o destino: IP da máquina/container e porta do processo. |
| `0.0.0.0` | Escutar nas interfaces IPv4 disponíveis no container; não é o endereço que o cliente deve usar como destino. |
| `AF_INET` / `SOCK_STREAM` | IPv4 e TCP, usados por cliente, servidor e proxy. |
| `AF_PACKET` / `SOCK_RAW` | Captura de quadros no Linux, usada pelo sniffer. |
| Payload | Os bytes de aplicação transportados, por exemplo `LOGIN Cadu senha123\n`. |
| Buffer | Dados já recebidos, guardados até completar a mensagem ou para a próxima leitura. |
| Thread | Fluxo de execução que atende uma sessão sem ocupar o laço principal de aceitação. |
| Região crítica | Trecho que usa um recurso compartilhado e precisa de coordenação; aqui, o log do proxy. |
| MITM | Intermediário que observa e pode alterar mensagens entre as pontas. |

## 3. `servico/protocolo.py`: as regras da conversa

Abra [protocolo.py](../servico/protocolo.py). Esse arquivo define:

- Endereço/porta padrão de escuta e contas de teste.
- `montar_login(usuario, senha)`: cria o texto `LOGIN ...\n` e o codifica em UTF-8, retornando bytes.
- `montar_quit()`: retorna os bytes `QUIT\n`.
- `interpretar_mensagem(linha)`: separa comando e argumentos por espaço e normaliza o comando para maiúsculas.

As respostas são 200 para credenciais corretas, 401 para incorretas, 400 para formato/comando inválido e BYE para encerrar. O serviço faz uma comparação com um dicionário, sem banco ou operação protegida após login.

**Por que a quebra de linha?** TCP não preserva o limite de cada `sendall`. Um LOGIN pode chegar em partes, ou duas mensagens podem chegar juntas. O `\n` define quando uma mensagem da aplicação terminou.

Não confunda o texto de dois caracteres `\n`, usado na documentação para representar a quebra, com o byte de quebra de linha realmente enviado.

## 4. `servico/cliente.py`: o que o cliente faz

Abra [cliente.py](../servico/cliente.py) e siga `main()`:

1. Lê endereço e porta do destino. Usuário/senha vêm de argumentos ou de `input()`.
2. Cria um socket TCP e chama `connect()`.
3. Cria um leitor com `cliente.makefile("r", encoding="utf-8", errors="replace")`.
4. Monta LOGIN e envia com `sendall()`.
5. Usa `readline()` para ler a resposta completa.
6. Envia QUIT, lê BYE e fecha os recursos ao sair dos blocos `with`.

`makefile` não troca sockets por um framework: cria uma interface de leitura com buffer sobre o mesmo socket. O envio continua usando o socket diretamente.

**Por que corrigimos o `recv` único?** `recv(4096)` pode retornar apenas `200 OK `, mesmo que o restante venha logo depois. `readline()` aguarda o delimitador e preserva os bytes excedentes. Não significa que a rede entregará um pacote inteiro por mensagem.

Na Fase 1 o destino é o servidor `.11:9999`. Na Fase 2 é o proxy `.12:8888`. O código do cliente é o mesmo.

O cliente atual imprime a resposta; ele não autentica o servidor nem confere se o usuário retornado é igual ao solicitado. Portanto, consegue exibir `200 OK Goku` depois de enviar Cadu.

## 5. `servico/servidor.py`: como o alvo responde

Abra [servidor.py](../servico/servidor.py). Em `main()`:

- `socket()` cria o socket de escuta.
- `SO_REUSEADDR` permite reutilizar o endereço com menos dificuldade ao reiniciar; não fornece segurança.
- `bind()` associa endereço e porta; `listen()` prepara a fila de conexões.
- `accept()` retorna um novo socket para conversar com um cliente.
- Uma thread executa `tratar_cliente()` para aquele socket.

Em `tratar_cliente()`, o servidor lê blocos com `recv`, acumula texto no buffer e separa as linhas com `\n`. Para cada linha:

- LOGIN com quantidade errada de argumentos gera 400.
- LOGIN com dois argumentos é comparado com `USUARIOS` e gera 200 ou 401.
- QUIT gera BYE e encerra o atendimento.
- Outro comando gera 400.

O servidor também possui timeout de 60 segundos. Ele registra as credenciais para fins didáticos. Esses logs ajudam a confirmar o resultado, mas a evidência de interceptação vem da captura de tráfego.

Uma limitação: ele decodifica UTF-8 antes de completar a linha. Caracteres multibyte divididos entre leituras podem ser substituídos; as contas do experimento usam ASCII. Não declare que esse parser cobre qualquer entrada arbitrária.

## 6. `proxy/proxy.py`: as funções que você deve dominar

### `main()`: configuração e aceitação

O `argparse` recebe quatro parâmetros posicionais: endereço/porta do proxy e endereço/porta do servidor. `--alterar` ativa a substituição; `--usuario` e `--senha` fornecem os valores. O que faltar é perguntado com `input()`.

As perguntas ocorrem **antes de `accept()` e antes de criar threads**. Assim, os clientes não disputam o teclado. Sem alteração, `login_substituto` fica `None`; com alteração, contém os bytes de um LOGIN completo.

A configuração rejeita campos vazios, whitespace e tamanho excessivo. Isso impede que uma credencial configurada contenha outra linha de comando.

Depois, o proxy cria seu socket de escuta. A thread principal permanece no laço `accept()` e inicia uma thread `daemon` para cada cliente, chamando `tratar_cliente()`.

### `tratar_cliente()`: recursos e erros de uma sessão

Essa função identifica a sessão por IP e porta de origem do cliente. Configura o timeout do socket aceito e abre outra conexão TCP com `socket.create_connection(..., timeout=TIMEOUT)`.

Com os dois sockets prontos, chama `encaminhar()`. Se ocorrer timeout, erro de rede ou erro de leitura/formato, registra a ocorrência. Os blocos `with` fecham os sockets e leitores da sessão. O `finally` registra seu encerramento.

O tratamento está dentro da thread da sessão, por isso um reset não encerra o laço que recebe novos clientes. O timeout é de espera por operação de rede, não uma duração máxima de toda a sessão.

### `ler_linha()`: delimitação e limite

Usa `readline(MAX_LINHA + 1)`. Pedir um byte além do limite permite distinguir uma linha de tamanho permitido de uma que passou de 4.096 bytes.

- Resultado vazio significa EOF: não há mais dados daquele lado.
- Linha acima do limite gera `ValueError`.
- Dados que terminam em EOF sem `\n` geram erro de linha incompleta.
- Uma linha completa retorna como bytes.

O kernel já organiza os segmentos TCP em ordem. A função precisa apenas reconhecer os limites das mensagens da aplicação. Ela não implementa remontagem de pacotes IP/TCP manualmente.

### `encaminhar()`: onde a alteração realmente acontece

A função cria leitores binários com buffer nos dois sockets e executa este ciclo:

1. Lê uma linha do cliente.
2. Se for EOF, encerra. Se for vazia, responde 400 sem enviá-la ao servidor, pois o servidor a ignoraria sem responder.
3. Divide os campos e verifica se é LOGIN com três campos não vazios.
4. Se houver substituição configurada, troca a linha pela mensagem de destino. Guarda a original apenas para registrar a alteração.
5. Envia a requisição ao servidor com `sendall()`.
6. Lê uma linha de resposta do servidor e a envia ao cliente.
7. Ao encaminhar BYE, encerra a sessão; caso contrário, aguarda outro comando.

Trecho central:

```python
original = requisicao
requisicao = login_substituto
log(sessao, f"ALTERACAO: original={original!r} modificada={requisicao!r}")
```

A linha enviada depois disso é `requisicao`, já modificada. O teste do servidor continua igual: ele não sabe que a mensagem anterior era diferente.

Não é preciso recalcular checksum nem ajustar sequência TCP: não estamos editando um segmento existente. O proxy termina uma conexão e envia dados por outra; as pilhas TCP do sistema operacional cuidam desses campos.

A leitura binária evita decodificar/recriar mensagens que só precisam ser encaminhadas. No modo normal, os bytes completos são preservados; o modo de alteração reconstrói apenas LOGIN correspondentes à regra.

### `log()`: a única região crítica do proxy

Todas as threads escrevem no mesmo terminal. `LOCK_LOG` protege um registro de cada vez, evitando mistura entre linhas.

O lock é liberado antes das operações de rede. Os buffers e sockets são próprios de cada sessão; não precisam de um lock global. `login_substituto` é um objeto `bytes` imutável, compartilhado somente para leitura.

## 7. Por que conseguimos atender vários clientes

Imagine três clientes: A envia LOGIN incompleto; B faz login normalmente; C desconecta. A thread de A espera seus bytes ou timeout. A thread de B continua a troca com o servidor. A thread de C encerra seus recursos. Enquanto isso, a thread principal continua aceitando conexões.

Os testes usam uma barreira: oito clientes precisam ter recebido suas respostas antes de qualquer um enviar QUIT. Isso comprova sessões simultâneas; um proxy estritamente sequencial não completaria essa barreira.

O GIL do Python não impede essa concorrência de I/O: uma thread esperando rede permite que outras avancem. Não estamos reivindicando paralelismo de cálculo pesado nem desempenho ilimitado.

## 8. Sniffer passivo versus proxy ativo

O [sniffer](../sniffer/sniffer.py) lê quadros brutos e decodifica cabeçalhos Ethernet, IPv4 e TCP para mostrar o payload. Não é o destino TCP do cliente e não envia mensagens do PLP. Precisa de Linux e capacidade `NET_RAW`.

O proxy é participante de duas conexões TCP. Ele pode modificar o conteúdo antes de enviá-lo pela segunda conexão, sem precisar de socket raw ou capacidade especial de captura.

O sniffer da Fase 1 compartilha a rede do servidor porque uma bridge não entrega automaticamente todo unicast a um observador independente. Já o proxy da Fase 2 possui IP próprio e está no caminho por configuração do cliente.

O sniffer não remonta fluxos TCP. Se uma credencial for dividida, pode aparecer em dois registros sem destaque automático. O proxy usa sockets TCP normais e espera a linha completa, por isso não tem essa mesma dependência de um LOGIN caber em um segmento.

## 9. O que o Podman acrescenta

Os Containerfiles empacotam os scripts em imagens Python. Não alteram a lógica do protocolo. Na Fase 2, `COPY` coloca o código dentro da imagem; editar o arquivo no host requer reconstruir a imagem e recriar o container.

`--internal` restringe acesso externo da rede. Não é criptografia nem autenticação. A rede interna ainda transporta texto claro entre os participantes e pode ser observada nos pontos de captura do laboratório.

Os scripts da Fase 2 usam nomes e sub-rede próprios. A montagem não remove recursos preexistentes. A limpeza remove apenas os containers nomeados dessa fase e tenta remover sua rede sem forçar a exclusão de outros participantes.

## 10. Como explicar as evidências

Abra a captura `docs/evidencias/fase2/fase2-alteracao.pcap` no Wireshark. Compare:

| Quadro | O que você mostra |
|---|---|
| 7 | Cliente envia Cadu/senha123 ao proxy. |
| 14 | Proxy envia Goku/testeteste ao servidor. |
| 16 | Servidor aceita Goku e retorna 200. |
| 18 | Cliente recebe essa resposta. |

Mostre os logs com original/modificada e o log de autenticação do servidor. São observações complementares: a captura mostra os bytes na rede, o proxy mostra a decisão de troca e o servidor confirma o processamento.

Existem dois fluxos TCP. “Seguir Fluxo” em apenas um deles não mostra as duas versões da mensagem. Compare os fluxos 0 e 1 da captura fornecida. Os números de quadros/fluxos podem mudar em uma nova execução.

O experimento usa contas de teste conhecidas. A conclusão é que a integridade da mensagem e a identidade do servidor não são verificadas pelo protocolo. Não diga que o ataque descobriu a senha de Goku ou que o servidor aceitou uma senha errada para Goku.

## 11. Perguntas prováveis na apresentação

**Por que isso é MITM se o cliente foi configurado para o proxy?** Porque ele se posiciona entre as pontas e pode ler/alterar a comunicação. O enunciado permite redirecionamento explícito por configuração; não exige ARP spoofing.

**O servidor continua autenticando?** Sim, compara as credenciais que chegaram. O problema demonstrado é que não detecta que esses bytes foram trocados antes de chegar, e o cliente não verifica a identidade do servidor.

**O proxy altera a resposta para fingir sucesso?** Não. Nesta implementação ele troca o LOGIN e retransmite a resposta real. Credencial de substituição errada gera 401.

**Por que a senha original errada pode receber 200 com o ataque ativo?** Porque o servidor recebe outra conta com uma senha correta, configurada no proxy. Não houve aceitação daquela senha original errada.

**Precisamos de threads em cada sentido?** Não para o PLP atual: cada sessão segue requisição e resposta. Uma thread por sessão consegue executar essa sequência. Um protocolo com mensagens espontâneas exigiria outro modelo de relay.

**O que é compartilhado entre threads?** Configuração imutável e saída do terminal. Só a saída precisa de lock. Sockets, buffers e dados em processamento são próprios de cada sessão.

**Um cliente malformado derruba o proxy?** Os casos testados encerram/rejeitam a sessão afetada e preservam as outras. Isso não é garantia de resistência a qualquer ataque de esgotamento: não há limite global de threads.

**O servidor sabe o IP original do cliente?** Vê o proxy como seu par TCP. Os logs do proxy identificam a conexão de entrada do cliente.

**Como demonstramos concorrência?** Com oito sessões sincronizadas nos testes locais e oito sessões simultâneas em um container cliente no Podman. O requisito é sobre conexões, não sobre quantidade de containers.

**Qual proteção viria depois?** Canal autenticado e com integridade, como TLS corretamente validado. Isso pertence à fase de defesa; não está implementado nesta etapa.

## 12. Roteiro curto para sua explicação oral

1. Apresente o PLP e o motivo didático de enviar credenciais em texto claro.
2. Desenhe cliente → proxy → servidor e explique as duas conexões TCP.
3. Mostre `main()` aceitando clientes e criando threads.
4. Mostre `tratar_cliente()` isolando recursos e erros por sessão.
5. Mostre `ler_linha()` e explique a diferença entre bytes TCP e mensagens completas.
6. Aponte a substituição em `encaminhar()` e o log de original/modificada.
7. Execute o mesmo login nos modos normal e de alteração.
8. Compare os dois fluxos na captura e confirme a conta autenticada no servidor.
9. Cite os 25 testes e o teste concorrente no Podman.
10. Termine indicando os limites: contas conhecidas, login sem recurso protegido, sem autenticação do servidor, sem limite global de threads e sem defesa implementada.

Para os comandos, use o [README](../README.md). Para os resultados e a conferência com os requisitos, use o [Relatório da Fase 2](Relatorio_Fase2.md).
