#!/usr/bin/env python3
"""Shell persistente do Heimdall Controls, pensado para leitor de tela.

Um único shell de verdade (zsh ou bash, num pseudoterminal) fica aberto: a pasta atual, as variáveis e os apelidos continuam de um comando
para o outro. Cada comando vira um "bloco" com o texto do comando, a saída limpa (sem cores nem códigos de tela), o estado e o código de saída.
Não há emulação de tela: nada de cursor nem de redesenho, só texto que o VoiceOver lê de cima para baixo.

Como saber que um comando acabou: o prompt do shell imprime uma marca com o código de saída e a pasta, e isso só acontece quando o shell volta a
aceitar comandos. Programas que perguntam algo (senha, sim ou não) recebem a resposta por enviar_texto(). interromper() é o Ctrl+C.
Um programa de tela cheia (vim, top) não serve aqui: interrompa e use a versão de texto (cat, sed, ps).
"""
import fcntl
import os
import pty
import re
import secrets
import signal
import struct
import subprocess
import tempfile
import termios
import threading
import time
from pathlib import Path

MAX_BLOCO = 1_000_000          # bytes guardados de saída por comando; o que passar disso é cortado, com aviso
MAX_BLOCOS = 300               # comandos guardados
MAX_LINHA_DIRETA = 800         # comando maior que isso (ou com várias linhas) vai por arquivo, porque o terminal limita a linha digitada
LARGURA = 120

# Sequências de controle que o terminal entende e o leitor de tela não deve ler: CSI (cores, cursor), OSC (título), e o resto.
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]|\x1b[()][A-Za-z0-9]")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def limpar_saida(texto: str) -> str:
    """Tira códigos de tela e controla o retorno de carro: barra de progresso que reescreve a linha fica só com a última versão."""
    texto = _ANSI.sub("", texto).replace("\r\n", "\n")
    linhas = []
    for l in texto.split("\n"):
        if "\r" in l:
            partes = [p for p in l.split("\r") if p != ""]
            l = partes[-1] if partes else ""
        linhas.append(_CTRL.sub("", l))
    return "\n".join(linhas)


def _sem_eco(comando: str, saida: str) -> str:
    """Alguns shells (zsh com o .zshrc do usuário) devolvem a linha digitada como primeira linha da saída: ela já aparece no cabeçalho, então sai daqui."""
    if "\n" not in comando.strip() and comando.strip():
        primeira, _, resto = saida.partition("\n")
        if primeira.strip() == comando.strip():
            return resto
    return saida


class Bloco:
    __slots__ = ("n", "comando", "saida", "estado", "codigo", "inicio", "fim", "cortado", "pasta", "versao", "interrompido")

    def __init__(self, n: int, comando: str, pasta: str):
        self.n, self.comando, self.pasta = n, comando, pasta
        self.saida, self.estado, self.codigo = "", "rodando", None
        self.inicio, self.fim, self.cortado, self.versao, self.interrompido = time.time(), None, False, 0, False

    def duracao(self) -> float:
        return (self.fim or time.time()) - self.inicio


class Shell:
    def __init__(self, pasta: str = "", comando_shell: str = "", ambiente: dict = None, inicio: str = "", carregar_rc: bool = False):
        self.pasta_inicial = pasta or str(Path.home())
        self.comando_shell = comando_shell or os.environ.get("SHELL") or "/bin/bash"
        self.ambiente_extra = ambiente or {}
        self.carregar_rc = carregar_rc            # True: lê o .zshrc ou .bashrc do usuário (apelidos, PATH); False: shell limpo (testes)
        self.inicio = inicio                      # comandos de preparo, rodados antes do primeiro bloco (por exemplo, carregar o heimdall.zsh)
        self.marca = "HD" + secrets.token_hex(6)
        self._re_marca = re.compile(r"@@" + self.marca + r"\|(\d+)\|([^|\n]*)\|@@\n?")
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self.blocos = []
        self.proximo = 1
        self.versao = 0                           # sobe a cada mudança, para o navegador saber o que buscar
        self.pasta = self.pasta_inicial
        self.pronto = False
        self._mestre = None
        self._proc = None
        self._buffer = ""
        self._atual = None
        self._leitor = None
        self._tmp = []

    # ------------------------------------------------------------------ ciclo de vida
    def iniciar(self) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                return
            mestre, escravo = pty.openpty()
            attrs = termios.tcgetattr(escravo)
            attrs[3] &= ~termios.ECHO                       # a digitação não volta como saída (senha também não aparece)
            termios.tcsetattr(escravo, termios.TCSANOW, attrs)
            fcntl.ioctl(escravo, termios.TIOCSWINSZ, struct.pack("HHHH", 50, LARGURA, 0, 0))
            env = dict(os.environ)
            env.update({"TERM": "dumb", "NO_COLOR": "1", "PAGER": "cat", "GIT_PAGER": "cat", "MANPAGER": "cat", "COLUMNS": str(LARGURA), "LINES": "50",
                        "HEIMDALL_CONTROLS": "1", "LANG": env.get("LANG") or "pt_BR.UTF-8"})
            env.update(self.ambiente_extra)
            nome = os.path.basename(self.comando_shell)
            if self.carregar_rc:
                cmd = [self.comando_shell, "-i"] if nome in ("zsh", "bash") else [self.comando_shell]
            else:
                cmd = [self.comando_shell, "-f"] if nome == "zsh" else [self.comando_shell, "--noprofile", "--norc"] if nome == "bash" else [self.comando_shell]
            self._proc = subprocess.Popen(cmd, stdin=escravo, stdout=escravo, stderr=escravo, cwd=self.pasta_inicial, env=env, close_fds=True,
                                          start_new_session=True, preexec_fn=lambda: fcntl.ioctl(0, termios.TIOCSCTTY, 0))
            os.close(escravo)
            self._mestre = mestre
            self._buffer, self._atual, self.pronto = "", None, False
            self._leitor = threading.Thread(target=self._ler, args=(mestre,), daemon=True)
            self._leitor.start()
            m = self.marca
            if nome == "zsh":
                # um gancho no começo guarda o código de saída e outro no fim põe o prompt, para temas do .zshrc não o trocarem
                prep = (f"unsetopt zle PROMPT_SP PROMPT_CR; setopt PROMPT_SUBST NO_BEEP; PROMPT_EOL_MARK=''; hd_a() {{ __hd=$?; }}; hd_z() {{ stty -echo 2>/dev/null; PS1=$'\\n@@{m}|${{__hd}}|${{PWD}}|@@\\n'; PS2=''; RPS1=''; RPROMPT=''; }}; "
                        "typeset -ag precmd_functions; precmd_functions=(hd_a ${precmd_functions:#hd_a} hd_z)")
            else:
                prep = f"PROMPT_COMMAND='__hd=$?; stty -echo 2>/dev/null'; PS1='\\n@@{m}|${{__hd}}|${{PWD}}|@@\\n'; PS2=''"
            os.write(mestre, (prep + "\n").encode())
        self._esperar_pronto(10)
        if self.inicio:
            self._rodar_interno(self.inicio)

    def _rodar_interno(self, texto: str, limite: int = 60) -> None:
        """Preparo do shell: roda sem aparecer na lista de comandos."""
        antes = len(self.blocos)
        self.executar(texto, registrar=False)
        self.esperar(limite)

    def _esperar_pronto(self, seg: float) -> None:
        fim = time.time() + seg
        with self._cond:
            while not self.pronto and time.time() < fim:
                self._cond.wait(0.2)

    def encerrar(self) -> None:
        with self._lock:
            p, self._proc = self._proc, None
            m, self._mestre = self._mestre, None
        if p and p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGHUP)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        if m is not None:
            try:
                os.close(m)
            except OSError:
                pass
        for t in self._tmp:
            try:
                os.unlink(t)
            except OSError:
                pass
        self._tmp = []
        with self._cond:
            if self._atual is not None and self._atual.estado == "rodando":
                self._fechar(self._atual, "encerrado", None)
            self.pronto = False
            self._cond.notify_all()

    def reiniciar(self) -> None:
        self.encerrar()
        self.iniciar()

    def vivo(self) -> bool:
        return bool(self._proc and self._proc.poll() is None)

    # ------------------------------------------------------------------ leitura
    def _ler(self, mestre: int) -> None:
        dec = __import__("codecs").getincrementaldecoder("utf-8")("replace")
        while True:
            try:
                dados = os.read(mestre, 65536)
            except OSError:
                dados = b""
            if not dados:
                break
            with self._cond:
                self._buffer += dec.decode(dados)
                self._processar()
        with self._cond:
            if self._atual is not None and self._atual.estado == "rodando" and self._mestre == mestre:
                self._fechar(self._atual, "encerrado", None)
            self.pronto = False
            self._cond.notify_all()

    def _processar(self) -> None:
        while True:
            m = self._re_marca.search(self._buffer)
            if not m:
                break
            antes = self._buffer[:m.start()]
            self._buffer = self._buffer[m.end():]
            self._juntar(antes)
            self.pasta = m.group(2) or self.pasta
            if self._atual is not None:
                self._fechar(self._atual, "concluido", int(m.group(1)))
            self.pronto = True
            self._cond.notify_all()
        # o que sobrou pode conter o começo de uma marca: só entrega o que certamente não é
        corte = self._buffer.rfind("@@")
        seguro = self._buffer if corte < 0 else self._buffer[:corte]
        if seguro:
            self._juntar(seguro)
            self._buffer = self._buffer[len(seguro):]

    def _juntar(self, texto: str) -> None:
        b = self._atual
        if b is None or not texto:
            return
        folga = MAX_BLOCO - len(b.saida)
        if folga <= 0:
            b.cortado = True
            return
        if len(texto) > folga:
            texto, b.cortado = texto[:folga], True
        b.saida += texto
        self.versao += 1
        b.versao = self.versao
        self._cond.notify_all()

    def _fechar(self, b: Bloco, estado: str, codigo) -> None:
        b.saida = limpar_saida(b.saida).strip("\n")
        if estado == "concluido" and b.interrompido:
            estado = "interrompido"
        b.estado, b.codigo, b.fim = estado, codigo, time.time()
        self.versao += 1
        b.versao = self.versao
        if self._atual is b:
            self._atual = None
        self._cond.notify_all()

    # ------------------------------------------------------------------ comandos
    def executar(self, comando: str, registrar: bool = True) -> Bloco:
        comando = comando.replace("\r\n", "\n").rstrip("\n")
        if not comando.strip():
            raise ValueError("comando vazio")
        if not self.vivo():
            self.iniciar()
        with self._lock:
            if self._atual is not None and self._atual.estado == "rodando":
                raise RuntimeError("Já há um comando em execução. Espere, responda a ele ou interrompa.")
            b = Bloco(self.proximo if registrar else 0, comando, self.pasta)
            if registrar:
                self.proximo += 1
                self.blocos.append(b)
                del self.blocos[:-MAX_BLOCOS]
            self._atual = b
            self.pronto = False
            self.versao += 1
            b.versao = self.versao
            if "\n" in comando or len(comando) > MAX_LINHA_DIRETA:
                f = tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, encoding="utf-8")
                f.write(comando + "\n")
                f.close()
                os.chmod(f.name, 0o600)
                self._tmp.append(f.name)
                self._tmp[:] = self._tmp[-20:]
                linha = f". '{f.name}'"
            else:
                linha = comando
            os.write(self._mestre, (linha + "\n").encode("utf-8"))
        return b

    def enviar_texto(self, texto: str) -> None:
        """Resposta a um programa em execução (pergunta de sim ou não, senha...). O texto não aparece na saída."""
        with self._lock:
            if self._atual is None or self._atual.estado != "rodando":
                raise RuntimeError("Nenhum comando está esperando resposta.")
            os.write(self._mestre, (texto.replace("\r", "").replace("\n", "") + "\n").encode("utf-8"))

    def interromper(self) -> bool:
        """Ctrl+C no que está rodando."""
        with self._lock:
            if self._atual is None or self._atual.estado != "rodando" or self._mestre is None:
                return False
            self._atual.interrompido = True       # o estado só muda quando o shell volta ao prompt; antes disso ainda há saída a chegar
            os.write(self._mestre, b"\x03")
            return True

    def esperar(self, seg: float) -> bool:
        """Espera o comando atual terminar (até seg segundos). True se não há mais nada rodando."""
        fim = time.time() + seg
        with self._cond:
            while self._atual is not None and self._atual.estado == "rodando" and time.time() < fim:
                self._cond.wait(0.1)
            return self._atual is None or self._atual.estado != "rodando"

    def rodando(self) -> bool:
        return self._atual is not None and self._atual.estado == "rodando"

    def limpar(self) -> None:
        with self._lock:
            self.blocos[:] = [b for b in self.blocos if b is self._atual]
            self.versao += 1

    def bloco(self, n: int):
        with self._lock:
            return next((b for b in self.blocos if b.n == n), None)

    def saida_parcial(self, b: Bloco) -> str:
        """Saída de um bloco ainda rodando, já sem códigos de tela."""
        with self._lock:
            return _sem_eco(b.comando, limpar_saida(b.saida) if b.estado == "rodando" else b.saida)

    def texto_para_copiar(self, ultimos: int = 1, com_comando: bool = True, so_bloco: int = 0) -> str:
        """Texto das últimas N saídas (ou de um bloco), do mais antigo para o mais novo, pronto para colar."""
        with self._lock:
            if so_bloco:
                escolhidos = [b for b in self.blocos if b.n == so_bloco]
            else:
                ultimos = max(1, min(int(ultimos), MAX_BLOCOS))
                escolhidos = self.blocos[-ultimos:]
            partes = []
            for b in escolhidos:
                saida = self.saida_parcial(b)
                cab = (f"$ {b.comando}\n" if com_comando else "")
                rod = "" if b.estado == "concluido" and b.codigo == 0 else f"\n[{b.estado}" + (f", código {b.codigo}" if b.codigo is not None else "") + "]"
                partes.append(cab + saida + rod + ("\n[saída cortada]" if b.cortado else ""))
            return "\n\n".join(partes)
