#!/usr/bin/env python3
"""Heimdall Learn, fase 2: modo aleatório. Sorteia um trecho do material da pasta, pergunta, corrige a resposta com base no trecho,
mostra a transcrição do trecho, grava o áudio (voz do macOS) e sugere matérias. Tudo fica em db/learn.db (tabela estudos).

A IA é o modelo local (ou a nuvem, se ligada em heimdall_perguntar). Sem modelo, o trecho é sorteado e fica registrado; a pergunta aparece como erro.
Usa só a biblioteca padrão do Python (pdftotext, se existir no Mac, para PDF).
"""
import html
import random
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import heimdall_learn_dados as dados
import heimdall_learn_tipos as tipos
import heimdall_learn_voz as voz

PROMPT = Path(__file__).resolve().parent / "prompts" / "prompt_learn_aleatorio.txt"
EXT_TEXTO = {".md", ".markdown", ".txt"}
TRECHO_MIN, TRECHO_MAX = 300, 1400
MAX_LIDO = 4 * 1024 * 1024
RECENTES = 30


def _limpa(t: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\r\n?", "\n", t or "")).strip()


def _sem_tags(x: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", x)))


def extrair_texto(p: Path) -> str:
    """Texto do documento (txt, md, docx, epub, pdf com pdftotext). Áudio e formatos desconhecidos dão ''. Nunca levanta erro."""
    ext = p.suffix.lower()
    try:
        if p.stat().st_size > 60 * 1024 * 1024:
            return ""
        if ext in EXT_TEXTO:
            return _limpa(p.read_bytes()[:MAX_LIDO].decode("utf-8", "replace"))
        if ext == ".docx":
            with zipfile.ZipFile(p) as z:
                xml = z.read("word/document.xml")[:MAX_LIDO * 3].decode("utf-8", "replace")
            return _limpa(_sem_tags(re.sub(r"</w:p>", "\n\n", xml)))
        if ext == ".epub":
            with zipfile.ZipFile(p) as z:
                nomes = sorted(n for n in z.namelist() if n.lower().endswith((".xhtml", ".html", ".htm")))
                blocos = []
                for n in nomes[:400]:
                    blocos.append(_sem_tags(re.sub(r"(?i)</(p|div|h[1-6]|li)>", "\n\n", z.read(n).decode("utf-8", "replace"))))
                    if sum(map(len, blocos)) > MAX_LIDO:
                        break
            return _limpa("\n\n".join(blocos))
        if ext == ".pdf" and shutil.which("pdftotext"):
            r = subprocess.run(["pdftotext", "-q", "-enc", "UTF-8", str(p), "-"], capture_output=True, timeout=120)
            return _limpa(r.stdout[:MAX_LIDO].decode("utf-8", "replace"))
    except (OSError, zipfile.BadZipFile, KeyError, subprocess.SubprocessError):
        return ""
    return ""


def dividir(texto: str) -> list:
    """Trechos de 300 a 1400 caracteres, juntando parágrafos; parágrafo maior que o limite é cortado na frase."""
    paragrafos = [x.strip() for x in re.split(r"\n\s*\n", texto) if x.strip()]
    saida, atual = [], ""
    for par in paragrafos:
        while len(par) > TRECHO_MAX:
            corte = max(par.rfind(". ", 0, TRECHO_MAX), par.rfind("\n", 0, TRECHO_MAX))
            corte = corte + 1 if corte > TRECHO_MIN else TRECHO_MAX
            if atual:
                saida.append(atual)
                atual = ""
            saida.append(par[:corte].strip())
            par = par[corte:].strip()
        if len(atual) + len(par) + 2 <= TRECHO_MAX:
            atual = (atual + "\n\n" + par).strip()
        else:
            if atual:
                saida.append(atual)
            atual = par
        if len(atual) >= TRECHO_MIN * 2:
            saida.append(atual)
            atual = ""
    if atual:
        saida.append(atual)
    return [t for t in saida if len(t) >= 80]


def _documentos_da_arvore(rel: str, limite: int = 6) -> list:
    """Documentos de texto da pasta e das subpastas (até `limite` níveis)."""
    achados, pendentes = [], [(rel, 0)]
    while pendentes:
        atual, nivel = pendentes.pop()
        for d in dados.listar_documentos(atual):
            if Path(d["nome"]).suffix.lower() in EXT_TEXTO | {".docx", ".epub", ".pdf"}:
                achados.append((atual, d["nome"]))
        if nivel < limite:
            for sub in dados.listar_pastas(atual):
                pendentes.append((sub["caminho"], nivel + 1))
    return achados


def _recentes(rel: str) -> set:
    con = dados.conectar()
    return {(r["documento"], r["trecho_idx"]) for r in con.execute(
        "SELECT documento, trecho_idx FROM estudos WHERE pasta = ? ORDER BY id DESC LIMIT ?", (rel, RECENTES)).fetchall()}


def sortear(rel: str, rng=None) -> dict:
    """Trecho aleatório do material da pasta, fora dos últimos sorteados. Levanta ErroLearn se não houver texto."""
    rng = rng or random
    pasta = dados.obter_pasta(rel)
    if not pasta:
        raise dados.ErroLearn("Pasta não encontrada.")
    docs = _documentos_da_arvore(pasta["caminho"])
    if not docs:
        raise dados.ErroLearn("Esta pasta ainda não tem documento de texto (txt, Markdown, Word, EPUB ou PDF). Importe material primeiro.")
    rng.shuffle(docs)
    recentes = _recentes(pasta["caminho"])
    reserva = None
    for pasta_doc, nome in docs[:8]:
        partes = dividir(extrair_texto(dados.pasta_no_disco(pasta_doc) / nome))
        if not partes:
            continue
        livres = [i for i in range(len(partes)) if (f"{pasta_doc}/{nome}", i) not in recentes]
        i = rng.choice(livres or range(len(partes)))
        achado = {"documento": f"{pasta_doc}/{nome}", "trecho_idx": i, "trecho": partes[i], "total": len(partes)}
        if livres:
            return achado
        reserva = reserva or achado
    if reserva:
        return reserva
    raise dados.ErroLearn("Não consegui extrair texto dos documentos desta pasta (PDF escaneado ou sem pdftotext?). Importe Markdown, texto, Word ou EPUB.")


def _sistema(pasta: dict) -> str:
    try:
        base = PROMPT.read_text(encoding="utf-8")
    except OSError:
        base = "Você é um tutor. Responda em português, sem formatação visual, só com base no TRECHO. {regras}"
    return base.replace("{regras}", tipos.regras_para_prompt(pasta["tipo"], pasta["categoria"], pasta.get("idioma", "")))


def _modelo(sistema: str, usuario: str, max_tokens: int = 700) -> str:
    import heimdall_perguntar as perguntar
    return perguntar.chamar_local(sistema, usuario, max_tokens=max_tokens)


def novo_estudo(rel: str, rng=None) -> int:
    """Sorteia o trecho e registra o estudo (sem IA ainda). Devolve o id."""
    pasta = dados.obter_pasta(rel)
    t = sortear(rel, rng)
    con = dados.conectar()
    with dados._trava:
        cur = con.execute("INSERT INTO estudos (pasta, documento, trecho_idx, trecho, estado, criado) VALUES (?, ?, ?, ?, 'sorteado', ?)",
                          (pasta["caminho"], t["documento"], t["trecho_idx"], t["trecho"], dados._agora()))
        con.commit()
    return cur.lastrowid


def obter(id_: int):
    r = dados.conectar().execute("SELECT * FROM estudos WHERE id = ?", (int(id_),)).fetchone()
    return dict(r) if r else None


def _gravar(id_: int, **campos) -> None:
    con = dados.conectar()
    with dados._trava:
        cols = ", ".join(f"{k} = ?" for k in campos)
        con.execute(f"UPDATE estudos SET {cols} WHERE id = ?", (*campos.values(), int(id_)))
        con.commit()


def gerar_pergunta(id_: int, modelo=None) -> None:
    """Pede ao modelo uma pergunta sobre o trecho. Guarda a pergunta ou o erro. Pensada para rodar em segundo plano."""
    e = obter(id_)
    pasta = dados.obter_pasta(e["pasta"])
    usuario = (f"TRECHO (de {e['documento']}):\n{e['trecho']}\n\nFaça UMA pergunta sobre este trecho, no estilo do tipo de estudo, que o aluno consiga responder por escrito. "
               "Não dê a resposta. Escreva só a pergunta.")
    try:
        p = (modelo or _modelo)(_sistema(pasta), usuario, 300).strip()
        if not p:
            raise RuntimeError("o modelo não respondeu")
        _gravar(id_, pergunta=p[:1200], estado="perguntado", erro="")
    except Exception as ex:  # noqa: BLE001
        _gravar(id_, estado="erro", erro=f"{type(ex).__name__}: {str(ex)[:150]}")


def corrigir(id_: int, resposta: str, modelo=None) -> None:
    """Corrige a resposta com base no trecho e sugere matérias. Guarda o resultado ou o erro."""
    resposta = " ".join((resposta or "").split())[:4000]
    if len(resposta) < 2:
        raise dados.ErroLearn("Escreva a sua resposta.")
    e = obter(id_)
    if not e or not e["pergunta"]:
        raise dados.ErroLearn("Esta pergunta ainda não está pronta.")
    pasta = dados.obter_pasta(e["pasta"])
    outras = ", ".join(p["nome"] for p in dados.arvore_plana() if p["caminho"] != e["pasta"])[:600]
    usuario = (f"TRECHO (de {e['documento']}):\n{e['trecho']}\n\nPERGUNTA: {e['pergunta']}\n\nRESPOSTA DO ALUNO: {resposta}\n\n"
               "Faça, nesta ordem e em texto corrido: 1) diga se a resposta está certa, parcial ou errada; 2) explique o que faltou ou o erro, com base no trecho; "
               "3) escreva a resposta ideal em poucas frases. Depois escreva a linha 'SUGESTÕES:' seguida de 2 a 4 matérias ou assuntos para estudar em seguida, separados por ponto e vírgula"
               + (f" (pastas que o aluno já tem: {outras})." if outras else "."))
    _gravar(id_, resposta=resposta, estado="corrigindo")
    try:
        t = (modelo or _modelo)(_sistema(pasta), usuario, 900).strip()
        if not t:
            raise RuntimeError("o modelo não respondeu")
        corpo, _, sug = t.partition("SUGESTÕES:")
        _gravar(id_, correcao=corpo.strip()[:4000], sugestoes=" ".join(sug.split())[:600], estado="corrigido", erro="")
    except Exception as ex:  # noqa: BLE001
        _gravar(id_, estado="erro_correcao", erro=f"{type(ex).__name__}: {str(ex)[:150]}")


def historico(rel: str = "", limite: int = 20) -> list:
    con = dados.conectar()
    if rel:
        rs = con.execute("SELECT id, pasta, documento, pergunta, estado, criado FROM estudos WHERE pasta = ? ORDER BY id DESC LIMIT ?", (dados.normalizar_caminho(rel), limite))
    else:
        rs = con.execute("SELECT id, pasta, documento, pergunta, estado, criado FROM estudos ORDER BY id DESC LIMIT ?", (limite,))
    return [dict(r) for r in rs.fetchall()]


# --- áudio (voz do macOS) -------------------------------------------------------------------------------
def pasta_audio() -> Path:
    return voz.pasta_audio()


def gravar_audio(id_: int) -> str:
    """Grava o trecho em áudio (voz do macOS, no idioma de estudo da pasta). Devolve '' se deu certo ou o motivo da falha."""
    e = obter(id_)
    if not e:
        return "estudo não encontrado"
    idioma = (dados.obter_pasta(e["pasta"]) or {}).get("idioma", "")
    base = pasta_audio() / f"estudo-{int(id_)}"
    motivo = voz.falar(e["trecho"], idioma, base)
    if not motivo:
        _gravar(id_, audio=base.name + ".m4a")
    return motivo


def caminho_audio(id_: int):
    e = obter(id_)
    if not e or not e["audio"] or not re.fullmatch(r"estudo-\d+\.m4a", e["audio"]):
        return None
    p = pasta_audio() / e["audio"]
    return p if p.is_file() and not p.is_symlink() else None
