# Relatório — Fase 1: Reconhecimento e Escuta Passiva

**Disciplina:** Laboratório de Redes de Computadores 
**Grupo:** Carlos Eduardo Alves Pereira Cunha, Bryan Melo Coelho e Eduardo Carlesso Silveira.

As evidências abaixo registram o experimento da Fase 1. Para os comandos atuais de montagem, execução e limpeza, consulte o [README](../README.md).

## 1. Resumo
O objetivo do trabalho é demonstrar, na prática, a quebra de confidencialidade de um protocolo de aplicação em texto claro. Para tal, criamos o PLP — PUC Login Protocol, através da montagem de um alvo cliente-servidor e de um interceptador passivo (sniffer) implementado com raw socket. Utilizamos como ferramenta de auxílio o Claude.

## 2. Topologia utilizada
Foi-se utilizado **Podman** para o trabalho. Por isso, a topologia de 3 nós prevista no enunciado (VM-cliente, VM-servidor, VM-observador) foi substituída por 3 containers Podman na mesma rede isolada, com uma adaptação na forma como o observador enxerga o tráfego, explicada a seguir.

**Rede:** `lab-net`, uma bridge Podman na sub-rede `192.168.200.0/24`. A montagem atual usa `--internal` para restringir acesso externo, com build das imagens realizado antes de criar a rede. As capturas deste relatório são anteriores a esse ajuste e, por si só, não comprovam a restrição de acesso externo.

| Nó         | Papel           | Container    | IP na `lab-net`                                                      | Observação                                                                                                                                                               |
| ---------- | --------------- | ------------ | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| servidor   | Servidor PLP    | `servidor`   | `192.168.200.11` (fixo)                                              | Sobe em background (`podman run -d --network lab-net --ip 192.168.200.11 ...`), permanece ativo durante toda a sessão de testes                                          |
| cliente    | Cliente PLP     | `cliente`    | dinâmico (`.2`, `.6`, `.7`, `.13` nos testes registrados na Seção 4) | Container efêmero (`--rm`): é criado, envia um único `LOGIN`/`QUIT` e é removido a cada execução; o Podman atribui automaticamente um IP livre da sub-rede a cada subida |
| observador | Sniffer passivo | `observador` | `192.168.200.11` (mesmo do servidor)                                 | Sobe com `--network container:servidor`, **compartilhando o namespace de rede** do container `servidor` em vez de ter uma identidade de rede própria                     |

### 2.1 Por que o observador compartilha a rede do servidor

A bridge do Podman funciona como um switch: estar na mesma sub-rede não garante receber o tráfego unicast entre outros containers. Por isso, apenas colocar um observador separado na rede não assegura a captura de cliente e servidor. A rede interna do VirtualBox também é um switch, com políticas próprias para permitir captura promíscua; não é um hub.

Para garantir visibilidade, o grupo optou por subir o `observador` com `--network container:servidor`, compartilhando sua interface e namespace de rede. Assim, o sniffer enxerga o tráfego do servidor e demonstra a exposição do conteúdo. Na captura Wireshark da seção 5, foi usada a bridge visível no host durante uma execução em modo rootful.

### 2.2. Modo de execução

Dentro da pasta do projeto, coloque:

```
bash podman/executar_podman.sh
```

Com isso, o servidor inicia.

Para abrir o observador, coloque em um terminal:

```
podman run -it --rm --name observador \
--network container:servidor \
--cap-add NET_RAW --cap-add NET_ADMIN \
-v "$(pwd)/sniffer:/app:Z" -w /app \
lab-sniffer python3 sniffer.py eth0 9999
```

Em outro terminal, para mandar mensagem para o servidor como cliente:

```
podman run --rm --name cliente \
--network lab-net \
-v "$(pwd)/servico:/app:Z" -w /app \
lab-servico python3 cliente.py 192.168.200.11 9999 Usuário Senha
```

Nota, os logins padrões até então são:
	"Cadu": "senha123",
	"Goku": "testeteste",
	"Gohan": "trabalhoLabRedes"
## 3. Protocolo implementado
O protocolo implementado é o PLP, PUC Login Protocol, um protocolo de aplicação próprio, criado especificamente para este trabalho, rodando sobre **TCP, na porta 9999**. Ele implementa um fluxo simples de autenticação (login), inspirado em protocolos de texto clássicos como SMTP/FTP: comandos em ASCII, uma linha por mensagem, terminados por `\n`.

### 3.1 Formato das mensagens PLP
**Cliente → Servidor**

```
LOGIN <usuario> <senha>
QUIT
```

- `LOGIN <usuario> <senha>`: solicita autenticação, enviando usuário e senha como dois campos separados por espaço, na mesma linha.
- `QUIT`: encerra a sessão.

**Servidor → Cliente**

```
200 OK <usuario>
401 UNAUTHORIZED
400 BAD_REQUEST
BYE
```

- `200 OK <usuario>`: credenciais corretas, autenticação bem-sucedida.
- `401 UNAUTHORIZED`: usuário não existe ou senha incorreta.
- `400 BAD_REQUEST`: mensagem malformada (comando desconhecido ou número de argumentos incorreto).
- `BYE`: confirmação do encerramento, enviada em resposta a `QUIT`.

### 3.2 Funcionamento

O servidor (`servico/servidor.py`) escuta conexões TCP na porta 9999 e aceita múltiplas conexões simultâneas (uma thread por cliente). Ao receber uma linha `LOGIN`, ele compara usuário e senha contra uma base fixa de usuários de teste definida em `servico/protocolo.py` (`Cadu`, `Goku`, `Gohan`) e responde de acordo. O cliente (`servico/cliente.py`) conecta-se ao servidor, envia um `LOGIN` com usuário/senha informados por parâmetro ou interativamente, imprime a resposta recebida, e em seguida envia `QUIT` para encerrar a sessão de forma organizada.

### 3.3 Por que o protocolo é vulnerável
O PLP foi desenhado intencionalmente sem nenhum mecanismo de proteção:
- Sem criptografia
- Sem autenticação do servidor
- Senha em texto claro, inclusive no servidor
- Sem proteção de integridade

## 4. Execução do experimento
Após o início do servidor, coloquei as mensagens de login do cliente em um novo terminal, e o sniffer capturou eles no processo. 

### Exemplo 1 — Saída 200
Entrada cliente:
```
     podman run --rm --name cliente \
       --network lab-net \
       -v "$(pwd)/servico:/app:Z" -w /app \
       lab-servico python3 cliente.py 192.168.200.11 9999 Cadu senha123
```

Saída cliente:
```
Conectando a 192.168.200.11:9999 ...
Enviando (texto claro): b'LOGIN Cadu senha123\n'
Resposta do servidor: 200 OK Cadu
Servidor: BYE
```

Saída sniffer:
```
--- pacote #7 [2026-10-03 16:19:58] ---
  192.168.200.2:41740 -> 192.168.200.11:9999
  payload bruto (texto claro): 'LOGIN Cadu senha123\n'
  >>> CREDENCIAIS INTERCEPTADAS: usuario='Cadu' senha='senha123'

--- pacote #9 [2026-10-03 16:19:58] ---
  192.168.200.11:9999 -> 192.168.200.2:41740
  payload bruto (texto claro): '200 OK Cadu\n'

--- pacote #11 [2026-10-03 16:19:58] ---
  192.168.200.2:41740 -> 192.168.200.11:9999
  payload bruto (texto claro): 'QUIT\n'

--- pacote #12 [2026-10-03 16:19:58] ---
  192.168.200.11:9999 -> 192.168.200.2:41740
  payload bruto (texto claro): 'BYE\n'
```

### Exemplo 2 — Saída 400
Entrada cliente:
```
     podman run --rm --name cliente   
     --network lab-net -v "$(pwd)/servico:/app:Z" -w /app   
     lab-servico python3 cliente.py 192.168.200.11 9999 "usuario com espaco" senha123

```

Saída cliente:
```
Conectando a 192.168.200.11:9999 ...
Enviando (texto claro): b'LOGIN usuario com espaco senha123\n'
Resposta do servidor: 400 BAD_REQUEST
Servidor: BYE
```

Saída sniffer:
```
--- pacote #67 [2026-10-03 16:29:08] ---
  192.168.200.6:41702 -> 192.168.200.11:9999
  payload bruto (texto claro): 'LOGIN usuario com espaco senha123\n'

--- pacote #69 [2026-10-03 16:29:08] ---
  192.168.200.11:9999 -> 192.168.200.6:41702
  payload bruto (texto claro): '400 BAD_REQUEST\n'

--- pacote #71 [2026-10-03 16:29:08] ---
  192.168.200.6:41702 -> 192.168.200.11:9999
  payload bruto (texto claro): 'QUIT\n'

--- pacote #72 [2026-10-03 16:29:08] ---
  192.168.200.11:9999 -> 192.168.200.6:41702
  payload bruto (texto claro): 'BYE\n'

```

### Exemplo 3 — Saída 401
Entrada cliente:
```
	podman run --rm --name cliente   
	--network lab-net   -v "$(pwd)/servico:/app:Z" -w /app   
	lab-servico python3 cliente.py 192.168.200.11 9999 Cadu senhaErrada
```

Saída cliente:
```
Conectando a 192.168.200.11:9999 ...
Enviando (texto claro): b'LOGIN Cadu senhaErrada\n'
Resposta do servidor: 401 UNAUTHORIZED
Servidor: BYE
```

Saída sniffer:
```
--- pacote #86 [2026-10-03 16:32:48] ---
  192.168.200.7:41254 -> 192.168.200.11:9999
  payload bruto (texto claro): 'LOGIN Cadu senhaErrada\n'
  >>> CREDENCIAIS INTERCEPTADAS: usuario='Cadu' senha='senhaErrada'

--- pacote #88 [2026-10-03 16:32:48] ---
  192.168.200.11:9999 -> 192.168.200.7:41254
  payload bruto (texto claro): '401 UNAUTHORIZED\n'

--- pacote #90 [2026-10-03 16:32:48] ---
  192.168.200.7:41254 -> 192.168.200.11:9999
  payload bruto (texto claro): 'QUIT\n'

--- pacote #91 [2026-10-03 16:32:48] ---
  192.168.200.11:9999 -> 192.168.200.7:41254
  payload bruto (texto claro): 'BYE\n'

```

## 5. Evidência de captura — Wireshark
A captura foi feita com o Wireshark rodando diretamente no host (com `sudo`, já que a rede `lab-net` do Podman roda em modo _rootful_ nesse cenário), na interface `podman1`. A bridge real do Podman visível no namespace de rede principal da máquina, com o filtro de exibição `tcp.port == 9999` aplicado. Em seguida, foi disparado um login válido pelo `cliente` (`Cadu`/`senha123`), e o Wireshark capturou a conversa TCP completa, pacotes **#67 a #79**:

|Pacote|Direção (porta origem → destino)|Flags|Len|Conteúdo de aplicação|
|---|---|---|---|---|
|67|192.168.200.2:36328 → 192.168.200.11:9999|SYN|0|— (abertura da conexão)|
|68|192.168.200.11:9999 → 192.168.200.2:36328|SYN, ACK|0|—|
|69|192.168.200.2:36328 → 192.168.200.11:9999|ACK|0|— (handshake concluído)|
|**70**|192.168.200.2:36328 → 192.168.200.11:9999|**PSH, ACK**|**20**|`LOGIN Cadu senha123\n`|
|71|192.168.200.11:9999 → 192.168.200.2:36328|ACK|0|— (confirmação de recebimento)|
|**72**|192.168.200.11:9999 → 192.168.200.2:36328|**PSH, ACK**|**12**|`200 OK Cadu\n`|
|73|192.168.200.2:36328 → 192.168.200.11:9999|ACK|0|—|
|**74**|192.168.200.2:36328 → 192.168.200.11:9999|**PSH, ACK**|**5**|`QUIT\n`|
|**75**|192.168.200.11:9999 → 192.168.200.2:36328|**PSH, ACK**|**4**|`BYE\n`|
|76–79|ambos os sentidos|FIN, ACK / ACK|0|— (encerramento da conexão TCP)|
![Pacotes da conversa PLP no Wireshark](Pasted%20image.png)


Os tamanhos dos quatro pacotes de dados são compatíveis com as mensagens do PLP. Essa correspondência de tamanho não basta para provar ausência de criptografia; a prova é a leitura dos bytes das credenciais no payload e no fluxo TCP, apresentada a seguir.

Ao clicar no pacote nº 70 e inspecionar o payload TCP, o conteúdo aparece integralmente legível em ASCII: `LOGIN Cadu senha123`, idêntico ao que o sniffer próprio já havia capturado no Exemplo 1 da Seção 4. O mesmo vale para a resposta do servidor no pacote nº 72, `200 OK Cadu`.

![Fluxo TCP com usuário e senha legíveis](Pasted%20image2.png)


## 6. Conclusão

A Fase 1 demonstrou a quebra de confidencialidade do PLP: o sniffer próprio com raw socket e a captura Wireshark mostraram usuário e senha legíveis na rede. O compartilhamento do namespace do servidor garantiu ao observador acesso ao tráfego necessário. O sniffer continua limitado à análise de payloads por segmento, sem remontagem do fluxo TCP; as instruções atuais e os limites estão no README e no guia do código.
