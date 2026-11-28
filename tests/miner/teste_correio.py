#!/usr/bin/env python3
"""Testa o módulo de Correio: contas, cofre por pessoa, leitura IMAP somente leitura (servidor simulado), regras de serviços e rotinas, marca de leitura e autenticação."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import tempfile
from datetime import date
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="correio_"))
os.environ["STUDIO_DB_DIR"] = str(TMP / "db")
os.environ["STUDIO_NUVEM_CHAVE"] = "chave-de-teste"
import studio_banco as banco  # noqa: E402
import studio_cidadania as cid  # noqa: E402
import studio_correio as cor  # noqa: E402
import studio_miner_dados as d  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({str(extra)[:400]})"))
    if not ok:
        falhas += 1


def cnj(seq, ano, j, tr, origem):
    base = f"{seq:07d}{ano}{j}{tr:02d}{origem:04d}"
    return f"{seq:07d}{98 - (int(base[:7] + base[7:] + '00') % 97):02d}{base[7:]}"


def bruto(de, assunto, corpo, mid, auth="mx.provedor.com; dmarc=pass header.from=jus.br; spf=pass; dkim=pass"):
    return (f"Authentication-Results: {auth}\r\nFrom: {de}\r\nSubject: {assunto}\r\nDate: Sat, 28 Nov 2026 08:00:00 -0300\r\nMessage-ID: <{mid}>\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n\r\n{corpo}\r\n").encode()


class FakeImap:
    """Servidor IMAP mínimo: guarda as chamadas para provar que só houve leitura."""
    def __init__(self, mensagens):
        self.m = mensagens   # uid -> bytes
        self.chamadas = []

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"']

    def select(self, pasta, readonly=False):
        self.chamadas.append(("select", pasta, readonly))
        return "OK", [b"1"]

    def response(self, nome):
        return nome, [b"777"]

    def uid(self, cmd, *args):
        self.chamadas.append((cmd,) + args)
        if cmd == "SEARCH":
            if args[1] == "UID":
                ini = int(args[2].split(":")[0])
                uids = [u for u in self.m if int(u) >= ini] or [max(self.m, key=int)]
            else:
                uids = list(self.m)
            return "OK", [" ".join(uids).encode()]
        if cmd == "FETCH":
            b = self.m[args[0]]
            if "HEADER.FIELDS" in args[1]:
                b = b.split(b"\r\n\r\n")[0] + b"\r\n\r\n"
            return "OK", [(b"1 (", b), b")"]
        return "NO", []

    def logout(self):
        pass


avisos = []


def pub(dado):
    novo = dado["id"] not in {a["id"] for a in avisos}
    if novo:
        avisos.append(dado)
    return {"novo": novo}


def ctx(imap):
    c = cid.Contexto(hoje=date(2026, 11, 28), publicar=pub, dormir=lambda s: None)
    c.conectar = lambda conta, senha: imap
    return c


# contas
try:
    cor.salvar({"provedor": "gmail", "usuario": "ana@gmail.com", "senha": ""})
    confere("conta sem senha é recusada", False)
except d.ErroMiner:
    confere("conta sem senha é recusada", True)
try:
    cor.salvar({"provedor": "outro", "usuario": "ana@x.com", "senha": "abc", "servidor": "127.0.0.1"})
    confere("servidor interno é recusado", False)
except d.ErroMiner:
    confere("servidor interno é recusado", True)
cor.salvar({"provedor": "gmail", "usuario": "ana@gmail.com", "senha": "abcd efgh ijkl mnop"})
conta = cor.contas()[0]
confere("conta guardada com servidor do provedor", conta["servidor"] == "imap.gmail.com")
confere("senha só no cofre, sem espaços", cid.segredo("correio_senha_" + conta["id"]) == "abcdefghijklmnop" and "abcd" not in str(cid.cfg("correio")))
with banco.da_pessoa("conv1"):
    confere("outra pessoa não vê a conta nem a senha", not cor.contas() and not cid.tem_segredo("correio_senha_" + conta["id"]))
confere("formulário não mostra a senha", "abcdefgh" not in cor.formulario("tok") and "type=\"password\"" in cor.formulario("tok"))

# rotinas
try:
    cor.salvar({"rotinas": "xx"})
    confere("rotina inválida é recusada", False)
except d.ErroMiner:
    confere("rotina inválida é recusada", True)
cor.salvar({"rotinas": "cobranca@empresa.com.br | fatura | Fatura da empresa"})

# leitura
num = cnj(1234, 2025, 8, 26, 100)
msgs = {
    "1": bruto("Tribunal <push@tjsp.jus.br>", "Andamento", f"Processo {num[:7]}-{num[7:9]}.{num[9:13]}.{num[13]}.{num[14:16]}.{num[16:]} teve movimentação.", "a1@x"),
    "2": bruto("Banco <spam@golpe.com>", "Promoção", "compre", "a2@x"),
    "3": bruto("Empresa <cobranca@empresa.com.br>", "Sua fatura chegou", "Valor da fatura 100", "a3@x", auth="mx.provedor.com; dmarc=fail"),
    "4": bruto("Falso <x@tjsp.jus.br>", "Andamento", f"Processo {num} movimentação", "a4@x", auth="mx.provedor.com; dmarc=fail"),
}
imap = FakeImap(msgs)
r = cor.executar(ctx(imap))
ids = [a["id"] for a in avisos]
confere("leitura devolve resultado e conta lida", r["novos"] >= 2 and r["parcial"] and not r["erros"], r)
confere("Push de remetente oficial com DMARC pass vira alerta", any(i.startswith("push:") for i in ids), ids)
confere("rotina do usuário vira alerta com aviso de remetente não confirmado", any(a["fonte"] == "correio" and "não confirmou" in a["resumo"] for a in avisos), avisos)
confere("DMARC falho não vira Push", sum(i.startswith("push:") for i in ids) == 1, ids)
confere("mensagem sem regra não vira alerta", not any("golpe.com" in a["resumo"] for a in avisos))
confere("só leitura: SELECT readonly e nenhuma escrita", all(c[2] is True for c in imap.chamadas if c[0] == "select") and {c[0] for c in imap.chamadas} <= {"select", "SEARCH", "FETCH"}, imap.chamadas)
confere("só BODY.PEEK", all("PEEK" in c[2] for c in imap.chamadas if c[0] == "FETCH"), imap.chamadas)
confere("assunto e remetente da mensagem sem regra não foram baixados por inteiro", not any(c[0] == "FETCH" and c[1] == "2" and "HEADER" not in c[2] for c in imap.chamadas), imap.chamadas)
n = len(avisos)
imap2 = FakeImap(msgs)
cor.executar(ctx(imap2))
confere("segunda rodada não repete nada (marca de leitura)", len(avisos) == n and any(c[0] == "SEARCH" and c[2] == "UID" for c in imap2.chamadas), imap2.chamadas)
msgs["5"] = bruto("Empresa <cobranca@empresa.com.br>", "Outra fatura", "Valor da fatura 200", "a5@x")
cor.executar(ctx(FakeImap(msgs)))
confere("mensagem nova gera só o novo alerta", len(avisos) == n + 1, len(avisos) - n)

# erros sem vazar a senha
class Recusa:
    pass


def nega(conta, senha):
    raise cor.imaplib.IMAP4.error("LOGIN failed " + senha)


c = cid.Contexto(hoje=date(2026, 11, 28), publicar=pub, dormir=lambda s: None)
c.conectar = nega
r = cor.executar(c)
confere("falha de login dá mensagem útil sem a senha", r["erros"] and "abcdefgh" not in r["erros"][0] and "senha de aplicativo" in r["erros"][0], r)

# registro por serviços
chamou = []
cor.registrar(lambda: [cor.Regra("teste", lambda m: m.dominio == "empresa.com.br", lambda m: chamou.append(m.assunto) or None, "teste")])
cor.executar(ctx(FakeImap({"9": bruto("a@empresa.com.br", "Algo", "x", "z@x")})))
confere("serviço registra regra e recebe só o que casa", chamou == ["Algo"], chamou)

# remoção
cor.remover({"id": conta["id"]})
confere("remover apaga conta e senha", not cor.contas() and not cid.tem_segredo("correio_senha_" + conta["id"]))

print("\nFALHAS:", falhas)
raise SystemExit(1 if falhas else 0)
