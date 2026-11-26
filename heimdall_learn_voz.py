#!/usr/bin/env python3
"""Voz do Studio Learn: fala (voz do macOS: say e afconvert) e escuta (transcrição local com Whisper).

Falar: texto vira .m4a, na voz do idioma (português, inglês, espanhol...). Só no Mac que hospeda o Heimdall.
Escutar: o áudio do aluno (gravado no navegador) é convertido e transcrito no próprio Mac; o áudio é apagado logo depois
(HEIMDALL_LEARN_GUARDAR_VOZ=1 guarda em db/voz, permissão só do dono). Nada sai do Mac.

Programas para a transcrição (um destes, mais um conversor de áudio):
  whisper-cli (brew install whisper-cpp) com o modelo em HEIMDALL_LEARN_WHISPER_MODELO (arquivo ggml-*.bin), ou mlx_whisper, ou whisper (pip).
  ffmpeg (brew install ffmpeg) ou o afconvert do macOS (não lê webm do Chrome; o Safari grava mp4 e funciona).
Usa só a biblioteca padrão do Python.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import heimdall_learn_dados as dados

CODIGOS = {"": "pt_BR", "português": "pt_BR", "portugues": "pt_BR", "inglês": "en_US", "ingles": "en_US", "espanhol": "es_ES", "francês": "fr_FR",
           "frances": "fr_FR", "alemão": "de_DE", "alemao": "de_DE", "italiano": "it_IT", "japonês": "ja_JP", "japones": "ja_JP"}
MAX_AUDIO = 25 * 1024 * 1024


def codigo_idioma(idioma: str) -> str:
    return CODIGOS.get(" ".join((idioma or "").lower().split()), "pt_BR")


def pasta_audio() -> Path:
    p = dados.pasta_dados() / "audio"
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    return p


def _voz(codigo: str) -> str:
    try:
        saida = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    vozes = []
    for ln in saida.splitlines():
        m = re.match(r"^(.+?)\s{2,}([a-z]{2}[_-][A-Za-z]{2})\b", ln)
        if m and m.group(2).replace("-", "_").lower() == codigo.lower():
            vozes.append(m.group(1).strip())
    vozes.sort(key=lambda v: ("Enhanced" not in v and "Premium" not in v, v))
    return vozes[0] if vozes else ""


def falar(texto: str, idioma: str, base: Path) -> str:
    """Grava base.m4a com a voz do macOS. Devolve '' se deu certo ou o motivo da falha."""
    if sys.platform != "darwin" or not shutil.which("say"):
        return "a voz do Mac só funciona no Mac que hospeda o Heimdall"
    try:
        import heimdall_voz
        texto = heimdall_voz.aplicar(texto)
    except Exception:  # noqa: BLE001
        pass
    codigo = codigo_idioma(idioma)
    voz = _voz(codigo) or _voz("pt_BR")
    try:
        cmd = ["say", "-o", str(base) + ".aiff"] + (["-v", voz] if voz else []) + ["-f", "-"]
        r = subprocess.run(cmd, input=texto[:6000].encode("utf-8"), capture_output=True, timeout=300)
        if r.returncode != 0:
            return "o say falhou: " + (r.stderr.decode("utf-8", "replace").strip()[:100] or "sem mensagem")
        c = subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", str(base) + ".aiff", str(base) + ".m4a"], capture_output=True, timeout=300)
        Path(str(base) + ".aiff").unlink(missing_ok=True)
        if c.returncode != 0:
            return "não consegui converter o áudio"
        os.chmod(str(base) + ".m4a", 0o600)
        return ""
    except (OSError, subprocess.SubprocessError) as ex:
        return "falha ao gravar: " + str(ex)[:100]


# --- escutar ------------------------------------------------------------------------------------------
def motor() -> tuple:
    """(nome, comando-base) do transcritor instalado, ou ('', [])."""
    modelo = os.environ.get("HEIMDALL_LEARN_WHISPER_MODELO", "").strip()
    if shutil.which("whisper-cli") and modelo and Path(modelo).expanduser().is_file():
        return "whisper-cli", ["whisper-cli", "-m", str(Path(modelo).expanduser()), "-nt", "-np"]
    if shutil.which("mlx_whisper"):
        return "mlx_whisper", ["mlx_whisper"]
    if shutil.which("whisper"):
        return "whisper", ["whisper"]
    return "", []


def disponivel() -> tuple:
    """(True, '') ou (False, motivo em português)."""
    nome, _ = motor()
    if not nome:
        return False, "Nenhum transcritor instalado no Mac. Instale com: brew install whisper-cpp ffmpeg (e aponte HEIMDALL_LEARN_WHISPER_MODELO para um modelo ggml)."
    if not (shutil.which("ffmpeg") or shutil.which("afconvert")):
        return False, "Falta um conversor de áudio (brew install ffmpeg)."
    return True, ""


def _converter(origem: Path, destino: Path) -> None:
    if shutil.which("ffmpeg"):
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(origem), "-ar", "16000", "-ac", "1", str(destino)], capture_output=True, timeout=120)
    else:
        r = subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(origem), str(destino)], capture_output=True, timeout=120)
    if r.returncode != 0 or not destino.is_file():
        raise RuntimeError("não consegui converter o áudio gravado (tente de novo ou use outro navegador)")


def _executar(cmd: list, timeout: int = 300) -> str:
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError("o transcritor falhou: " + r.stderr.decode("utf-8", "replace").strip()[:120])
    return r.stdout.decode("utf-8", "replace")


def transcrever(audio: bytes, idioma: str = "", executor=None, conversor=None) -> str:
    """Transcreve o áudio do aluno no Mac. `executor` e `conversor` existem para teste. Levanta dados.ErroLearn com mensagem em português."""
    if not audio or len(audio) < 200:
        raise dados.ErroLearn("A gravação veio vazia. Tente de novo.")
    if len(audio) > MAX_AUDIO:
        raise dados.ErroLearn("A gravação é grande demais (máximo de 25 MB).")
    if executor is None:
        ok, motivo = disponivel()
        if not ok:
            raise dados.ErroLearn(motivo)
    nome, base = motor() if executor is None else ("teste", ["whisper"])
    lang = "" if idioma == "auto" else codigo_idioma(idioma).split("_")[0]
    with tempfile.TemporaryDirectory(prefix="learn-voz-") as tmp:
        os.chmod(tmp, 0o700)
        bruto, wav = Path(tmp) / "entrada", Path(tmp) / "entrada.wav"
        bruto.write_bytes(audio)
        os.chmod(bruto, 0o600)
        try:
            (conversor or _converter)(bruto, wav)
            if nome == "whisper-cli":
                cmd = base + ["-l", lang or "auto", "-f", str(wav)]
            elif nome == "mlx_whisper":
                cmd = base + [str(wav)] + (["--language", lang] if lang else []) + ["--output-format", "txt", "--output-dir", tmp]
            else:
                cmd = base + [str(wav)] + (["--language", lang] if lang else []) + ["--model", os.environ.get("HEIMDALL_LEARN_WHISPER_TAMANHO", "small"), "--output_format", "txt", "--output_dir", tmp]
            saida = (executor or _executar)(cmd)
            if nome != "whisper-cli":
                txt = Path(tmp) / "entrada.txt"
                if txt.is_file():
                    saida = txt.read_text(encoding="utf-8", errors="replace")
        except (RuntimeError, OSError, subprocess.SubprocessError) as ex:
            raise dados.ErroLearn(str(ex)[:160])
        if os.environ.get("HEIMDALL_LEARN_GUARDAR_VOZ", "0") == "1":
            pasta = dados.pasta_dados() / "voz"
            pasta.mkdir(parents=True, exist_ok=True, mode=0o700)
            destino = pasta / f"voz-{int(__import__('time').time())}.audio"
            destino.write_bytes(audio)
            os.chmod(destino, 0o600)
    texto = " ".join(re.sub(r"\[[^\]]*\]", " ", saida).split())
    if not texto:
        raise dados.ErroLearn("Não entendi nada na gravação. Fale mais perto do microfone e tente de novo.")
    return texto[:2000]
