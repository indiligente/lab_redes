"""Testes TCP locais do proxy, usando apenas a biblioteca padrao."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest


RAIZ = Path(__file__).resolve().parents[1]
LOGIN = b"LOGIN Cadu senha123\n"
OK = b"200 OK Cadu\n"


def porta_livre():
    with socket.socket() as conexao:
        conexao.bind(("127.0.0.1", 0))
        return conexao.getsockname()[1]


class TestProxy(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory(prefix="teste-proxy-")
        self.addCleanup(pasta.cleanup)
        self.pasta = Path(pasta.name)
        self.numero_log = 0
        self.porta_servidor = porta_livre()
        self.processo_servidor, self.log_servidor = self.iniciar_servidor(self.porta_servidor)
        self.porta_proxy, self.processo_proxy, self.log_proxy = self.iniciar_proxy(self.porta_servidor)

    def iniciar(self, argumentos, mensagem_pronta, entrada=None):
        self.numero_log += 1
        caminho = self.pasta / f"processo-{self.numero_log}.log"
        with caminho.open("wb") as saida:
            processo = subprocess.Popen(
                [sys.executable, "-B", "-u", *argumentos],
                stdout=saida, stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE if entrada is not None else subprocess.DEVNULL,
            )
        self.addCleanup(self.parar, processo)
        if entrada is not None:
            processo.stdin.write(entrada.encode())
            processo.stdin.close()
        for _ in range(100):
            conteudo = caminho.read_text(errors="replace")
            if mensagem_pronta in conteudo:
                return processo, caminho
            if processo.poll() is not None:
                self.fail(conteudo)
            time.sleep(0.02)
        self.fail(f"Processo nao iniciou: {caminho.read_text()}")

    @staticmethod
    def parar(processo):
        if processo.poll() is None:
            processo.terminate()
        try:
            processo.wait(timeout=3)
        except subprocess.TimeoutExpired:
            processo.kill()
            processo.wait(timeout=3)

    def iniciar_servidor(self, porta):
        return self.iniciar(
            [str(RAIZ / "servico/servidor.py"), "127.0.0.1", str(porta)],
            "Servidor PLP escutando",
        )

    def iniciar_proxy(self, porta_servidor, timeout=2, alterar=False,
                      usuario="Goku", senha="testeteste", entrada=None):
        porta = porta_livre()
        # Reduz apenas o timeout do processo de teste; em uso normal sao 60s.
        codigo = (
            f"import sys; sys.path.insert(0, {str(RAIZ / 'proxy')!r}); "
            f"import proxy; proxy.TIMEOUT = {timeout!r}; proxy.main()"
        )
        argumentos = ["-c", codigo, "127.0.0.1", str(porta), "127.0.0.1", str(porta_servidor)]
        if alterar:
            argumentos.append("--alterar")
            if usuario is not None:
                argumentos.extend(["--usuario", usuario])
            if senha is not None:
                argumentos.extend(["--senha", senha])
        processo, caminho = self.iniciar(argumentos, "Proxy PLP em", entrada)
        return porta, processo, caminho

    def conectar(self, porta):
        return socket.create_connection(("127.0.0.1", porta), timeout=3)

    def login(self, porta=None, usuario="Cadu", senha="senha123"):
        with self.conectar(porta or self.porta_proxy) as cliente, cliente.makefile("rb") as respostas:
            cliente.sendall(f"LOGIN {usuario} {senha}\n".encode())
            self.assertEqual(respostas.readline(), f"200 OK {usuario}\n".encode())
            cliente.sendall(b"QUIT\n")
            self.assertEqual(respostas.readline(), b"BYE\n")

    def assert_encerrada(self, cliente):
        try:
            self.assertEqual(cliente.recv(4096), b"")
        except ConnectionResetError:
            pass  # Fechamento com dados nao lidos pode gerar RST no TCP.

    def destino_controlado(self, timeout=2):
        destino = socket.socket()
        self.addCleanup(destino.close)
        destino.bind(("127.0.0.1", 0))
        destino.listen()
        destino.settimeout(3)
        porta, processo, _ = self.iniciar_proxy(destino.getsockname()[1], timeout)
        return destino, porta, processo

    def recuperar(self, destino, porta, processo):
        # Confirma que o MESMO proxy atende uma nova sessao apos a falha.
        self.assertIsNone(processo.poll())
        with self.conectar(porta) as cliente, destino.accept()[0] as servidor:
            servidor.settimeout(3)
            with cliente.makefile("rb") as respostas, servidor.makefile("rb") as pedidos:
                cliente.sendall(LOGIN)
                self.assertEqual(pedidos.readline(), LOGIN)
                servidor.sendall(OK)
                self.assertEqual(respostas.readline(), OK)
                cliente.sendall(b"QUIT\n")
                self.assertEqual(pedidos.readline(), b"QUIT\n")
                servidor.sendall(b"BYE\n")
                self.assertEqual(respostas.readline(), b"BYE\n")

    def test_cliente_real_200_401_400(self):
        for usuario, senha, esperado in [
            ("Cadu", "senha123", "200 OK Cadu"),
            ("Cadu", "errada", "401 UNAUTHORIZED"),
            ("usuario com espaco", "senha123", "400 BAD_REQUEST"),
        ]:
            with self.subTest(resposta=esperado):
                resultado = subprocess.run(
                    [sys.executable, "-B", str(RAIZ / "servico/cliente.py"),
                     "127.0.0.1", str(self.porta_proxy), usuario, senha],
                    capture_output=True, text=True, timeout=5,
                )
                self.assertEqual(resultado.returncode, 0, resultado.stderr)
                self.assertIn(f"Resposta do servidor: {esperado}\n", resultado.stdout)
                self.assertIn("Servidor: BYE\n", resultado.stdout)

    def test_oito_sessoes_simultaneas_sem_misturar_respostas(self):
        barreira = threading.Barrier(8)
        contas = [("Cadu", "senha123"), ("Goku", "testeteste"), ("Gohan", "trabalhoLabRedes")]

        def sessao(indice):
            usuario, senha = contas[indice % len(contas)]
            with self.conectar(self.porta_proxy) as cliente, cliente.makefile("rb") as respostas:
                cliente.sendall(f"LOGIN {usuario} {senha}\n".encode())
                self.assertEqual(respostas.readline(), f"200 OK {usuario}\n".encode())
                # Nenhum cliente sai antes de todos terem recebido seu LOGIN.
                barreira.wait(timeout=2)
                cliente.sendall(b"QUIT\n")
                self.assertEqual(respostas.readline(), b"BYE\n")

        with ThreadPoolExecutor(max_workers=8) as tarefas:
            list(tarefas.map(sessao, range(8)))

    def test_cliente_com_linha_pendente_nao_bloqueia_outros(self):
        with self.conectar(self.porta_proxy) as lento:
            lento.sendall(b"LOGIN Cadu ")
            self.login()
            lento.sendall(b"senha123\nQUIT\n")
            with lento.makefile("rb") as respostas:
                self.assertEqual(respostas.readline(), OK)
                self.assertEqual(respostas.readline(), b"BYE\n")

    def test_linhas_fragmentadas_e_agrupadas(self):
        with self.conectar(self.porta_proxy) as cliente, cliente.makefile("rb") as respostas:
            cliente.sendall(b"LOGIN Cadu ")
            time.sleep(0.03)
            cliente.sendall(b"senha123\nINVALIDO\nQUIT\n")
            self.assertEqual(
                [respostas.readline() for _ in range(3)],
                [OK, b"400 BAD_REQUEST\n", b"BYE\n"],
            )

    def test_malformadas_e_vazias_nao_impedem_login(self):
        with self.conectar(self.porta_proxy) as cliente, cliente.makefile("rb") as respostas:
            cliente.sendall(b"INVALIDO\nLOGIN so_usuario\n\n  \n" + LOGIN + b"QUIT\n")
            self.assertEqual(
                [respostas.readline() for _ in range(6)],
                [b"400 BAD_REQUEST\n"] * 4 + [OK, b"BYE\n"],
            )

    def test_linha_grande_encerra_apenas_sua_sessao(self):
        with self.conectar(self.porta_proxy) as cliente:
            cliente.sendall(b"X" * 4097)
            self.assert_encerrada(cliente)
        self.login()

    def test_cliente_fecha_com_linha_incompleta(self):
        with self.conectar(self.porta_proxy) as cliente:
            cliente.sendall(b"LOGIN Cadu ")
            cliente.shutdown(socket.SHUT_WR)
            self.assert_encerrada(cliente)
        self.login()

    def test_reset_do_cliente(self):
        with self.conectar(self.porta_proxy) as cliente:
            cliente.sendall(b"LOGIN Cadu ")
            cliente.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        self.login()
        self.assertIsNone(self.processo_proxy.poll())

    def test_timeout_do_cliente(self):
        porta, processo, _ = self.iniciar_proxy(self.porta_servidor, timeout=0.3)
        with self.conectar(porta) as cliente:
            cliente.sendall(b"LOGIN Cadu ")
            self.assert_encerrada(cliente)
        self.login(porta)
        self.assertIsNone(processo.poll())

    def test_timeout_do_servidor(self):
        destino, porta, processo = self.destino_controlado(timeout=0.3)
        with self.conectar(porta) as cliente, destino.accept()[0] as servidor:
            servidor.settimeout(3)
            cliente.sendall(LOGIN)
            self.assertEqual(servidor.recv(4096), LOGIN)
            self.assert_encerrada(cliente)  # Destino nao envia resposta.
        self.recuperar(destino, porta, processo)

    def test_resposta_incompleta_do_servidor(self):
        destino, porta, processo = self.destino_controlado()
        with self.conectar(porta) as cliente:
            servidor, _ = destino.accept()
            with servidor:
                servidor.settimeout(3)
                cliente.sendall(LOGIN)
                self.assertEqual(servidor.recv(4096), LOGIN)
                servidor.sendall(b"200 OK")
            self.assert_encerrada(cliente)
        self.recuperar(destino, porta, processo)

    def test_reset_do_servidor(self):
        destino, porta, processo = self.destino_controlado()
        with self.conectar(porta) as cliente:
            servidor, _ = destino.accept()
            with servidor:
                servidor.settimeout(3)
                cliente.sendall(LOGIN)
                self.assertEqual(servidor.recv(4096), LOGIN)
                servidor.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            self.assert_encerrada(cliente)
        self.recuperar(destino, porta, processo)

    def test_servidor_indisponivel_e_recuperacao(self):
        porta_destino = porta_livre()
        porta, processo, _ = self.iniciar_proxy(porta_destino)
        with self.conectar(porta) as cliente:
            self.assert_encerrada(cliente)
        self.iniciar_servidor(porta_destino)
        self.login(porta)
        self.assertIsNone(processo.poll())

    def test_preserva_bytes_e_respostas_fragmentadas(self):
        destino, porta, _ = self.destino_controlado()
        with self.conectar(porta) as cliente, destino.accept()[0] as servidor:
            servidor.settimeout(3)
            with cliente.makefile("rb") as respostas, servidor.makefile("rb") as pedidos:
                cliente.sendall(b"LOGIN  Cadu senha123\r\n")
                self.assertEqual(pedidos.readline(), b"LOGIN  Cadu senha123\r\n")
                servidor.sendall(b"200 OK ")
                time.sleep(0.03)
                servidor.sendall(b"Cadu\r\n")
                self.assertEqual(respostas.readline(), b"200 OK Cadu\r\n")
                cliente.sendall(b"QUIT\n")
                self.assertEqual(pedidos.readline(), b"QUIT\n")
                servidor.sendall(b"BYE\n")
                self.assertEqual(respostas.readline(), b"BYE\n")

    def test_alteracao_aceita_pelo_servidor_e_cliente_real(self):
        porta, _, caminho_log = self.iniciar_proxy(self.porta_servidor, alterar=True)
        resultado = subprocess.run(
            [sys.executable, "-B", str(RAIZ / "servico/cliente.py"),
             "127.0.0.1", str(porta), "Cadu", "senha123"],
            capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("Enviando (texto claro): b'LOGIN Cadu senha123\\n'", resultado.stdout)
        self.assertIn("Resposta do servidor: 200 OK Goku\n", resultado.stdout)
        self.assertIn("Servidor: BYE\n", resultado.stdout)
        log_servidor = self.log_servidor.read_text()
        self.assertIn("autenticacao OK para 'Goku'", log_servidor)
        self.assertNotIn("autenticacao OK para 'Cadu'", log_servidor)
        log_proxy = caminho_log.read_text()
        self.assertIn("ALTERACAO: original=b'LOGIN Cadu senha123\\n'", log_proxy)
        self.assertIn("modificada=b'LOGIN Goku testeteste\\n'", log_proxy)
        self.assertNotIn("Usuario de substituicao:", log_proxy)
        self.assertNotIn("Senha de substituicao:", log_proxy)

    def test_alteracao_so_atinge_login_valido(self):
        porta, _, caminho_log = self.iniciar_proxy(self.porta_servidor, alterar=True)
        with self.conectar(porta) as cliente, cliente.makefile("rb") as respostas:
            cliente.sendall(
                b"LOGIN Cadu errada\nLOGIN Gohan trabalhoLabRedes\n"
                b"LOGIN so_usuario\nINVALIDO\nQUIT\n"
            )
            self.assertEqual(
                [respostas.readline() for _ in range(5)],
                [b"200 OK Goku\n", b"200 OK Goku\n",
                 b"400 BAD_REQUEST\n", b"400 BAD_REQUEST\n", b"BYE\n"],
            )
        self.assertEqual(caminho_log.read_text().count("ALTERACAO:"), 2)

    def test_alteracao_com_login_fragmentado_e_comandos_agrupados(self):
        porta, _, _ = self.iniciar_proxy(self.porta_servidor, alterar=True)
        with self.conectar(porta) as cliente, cliente.makefile("rb") as respostas:
            cliente.sendall(b"LOGIN Cadu ")
            time.sleep(0.03)
            cliente.sendall(b"senha123\nLOGIN Gohan trabalhoLabRedes\nQUIT\n")
            self.assertEqual(
                [respostas.readline() for _ in range(3)],
                [b"200 OK Goku\n", b"200 OK Goku\n", b"BYE\n"],
            )

    def test_alteracao_com_oito_sessoes_simultaneas(self):
        porta, _, _ = self.iniciar_proxy(self.porta_servidor, alterar=True)
        barreira = threading.Barrier(8)

        def sessao(indice):
            pedido, esperado = (
                (LOGIN, b"200 OK Goku\n") if indice % 2 == 0
                else (b"LOGIN Gohan trabalhoLabRedes\n", b"200 OK Goku\n")
            )
            with self.conectar(porta) as cliente, cliente.makefile("rb") as respostas:
                cliente.sendall(pedido)
                self.assertEqual(respostas.readline(), esperado)
                barreira.wait(timeout=2)
                cliente.sendall(b"QUIT\n")
                self.assertEqual(respostas.readline(), b"BYE\n")

        with ThreadPoolExecutor(max_workers=8) as tarefas:
            list(tarefas.map(sessao, range(8)))

    def test_modos_normal_e_alteracao_independentes(self):
        porta_alteracao, _, _ = self.iniciar_proxy(self.porta_servidor, alterar=True)
        with self.conectar(self.porta_proxy) as normal, self.conectar(porta_alteracao) as alterado:
            with normal.makefile("rb") as resposta_normal, alterado.makefile("rb") as resposta_alterada:
                normal.sendall(LOGIN)
                alterado.sendall(LOGIN)
                self.assertEqual(resposta_normal.readline(), OK)
                self.assertEqual(resposta_alterada.readline(), b"200 OK Goku\n")
                normal.sendall(b"QUIT\n")
                alterado.sendall(b"QUIT\n")
                self.assertEqual(resposta_normal.readline(), b"BYE\n")
                self.assertEqual(resposta_alterada.readline(), b"BYE\n")

    def test_cliente_interativo(self):
        resultado = subprocess.run(
            [sys.executable, "-B", str(RAIZ / "servico/cliente.py"),
             "127.0.0.1", str(self.porta_proxy)],
            input="Cadu\nsenha123\n", capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("Resposta do servidor: 200 OK Cadu\n", resultado.stdout)
        self.assertIn("Servidor: BYE\n", resultado.stdout)

    def conferir_alteracao(self, porta, esperado):
        with self.conectar(porta) as cliente, cliente.makefile("rb") as respostas:
            cliente.sendall(LOGIN)
            self.assertEqual(respostas.readline(), esperado)
            cliente.sendall(b"QUIT\n")
            self.assertEqual(respostas.readline(), b"BYE\n")

    def test_credenciais_personalizadas_por_parametros(self):
        porta, _, _ = self.iniciar_proxy(
            self.porta_servidor, alterar=True, usuario="Gohan", senha="trabalhoLabRedes",
        )
        self.conferir_alteracao(porta, b"200 OK Gohan\n")

    def test_proxy_interativo(self):
        porta, _, caminho = self.iniciar_proxy(
            self.porta_servidor, alterar=True, usuario=None, senha=None,
            entrada="Gohan\ntrabalhoLabRedes\n",
        )
        self.conferir_alteracao(porta, b"200 OK Gohan\n")
        conteudo = caminho.read_text()
        self.assertEqual(conteudo.count("Usuario de substituicao:"), 1)
        self.assertEqual(conteudo.count("Senha de substituicao:"), 1)

    def test_parametro_e_entrada_interativa_combinados(self):
        porta, _, caminho = self.iniciar_proxy(
            self.porta_servidor, alterar=True, usuario="Gohan", senha=None,
            entrada="trabalhoLabRedes\n",
        )
        self.conferir_alteracao(porta, b"200 OK Gohan\n")
        self.assertNotIn("Usuario de substituicao:", caminho.read_text())
        self.assertEqual(caminho.read_text().count("Senha de substituicao:"), 1)

    def test_senha_de_substituicao_errada_recebe_401(self):
        porta, _, _ = self.iniciar_proxy(
            self.porta_servidor, alterar=True, usuario="Gohan", senha="errada",
        )
        self.conferir_alteracao(porta, b"401 UNAUTHORIZED\n")

    def test_rejeita_configuracoes_invalidas(self):
        base = [sys.executable, "-B", str(RAIZ / "proxy/proxy.py"),
                "127.0.0.1", "0", "127.0.0.1", str(self.porta_servidor)]
        casos = [
            (["--usuario", "Goku"], "exigem --alterar"),
            (["--alterar"], "Informe as credenciais"),
            (["--alterar", "--usuario", "", "--senha", "teste"], "devem ser preenchidos"),
            (["--alterar", "--usuario", "com espaco", "--senha", "teste"], "nao podem conter"),
            (["--alterar", "--usuario", "Goku", "--senha", "x\nQUIT"], "nao podem conter"),
            (["--alterar", "--usuario", "Goku", "--senha", "x" * 4096], "excede 4096"),
        ]
        for argumentos, mensagem in casos:
            with self.subTest(argumentos=argumentos[:2], erro=mensagem):
                resultado = subprocess.run(
                    base + argumentos, input="", capture_output=True, text=True, timeout=3,
                )
                self.assertEqual(resultado.returncode, 2, resultado.stdout)
                self.assertIn(mensagem, resultado.stderr)


if __name__ == "__main__":
    unittest.main()
