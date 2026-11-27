#!/usr/bin/env python3
"""Traz para a aba Avisos do Studio Health e do Studio Finance as notas de saúde e finanças que o Heimdall já tinha gravado, e apaga as originais.

Onde elas estão: (1) a cópia em Markdown no cofre (pastas saude e heimdall-financas, com os áudios na subpasta audio); (2) a nota no app Notas:
pasta Saúde dentro de Heimdall-ai e pasta Heimdall Finanças. Ordem, para nada se perder: importa tudo, CONFERE que cada item está nos avisos,
e só então apaga. O app Notas manda a nota apagada para "Apagadas recentemente", de onde dá para recuperá-la por 30 dias.
Só mexe nas pastas do Heimdall: uma pasta sua chamada Saúde fora de Heimdall-ai nunca é tocada. Pode rodar de novo: não duplica.
Uso: python3 migrar_avisos.py            (só mostra o que faria)
     python3 migrar_avisos.py --executar  (importa, confere e apaga)
"""
import argparse
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import heimdall_avisos as av  # noqa: E402

# serviço -> (pasta do cofre, nome da pasta no app Notas, True se fica dentro da pasta-raiz Heimdall-ai)
ORIGENS = {"saude": ("saude", "Saúde", True), "financas": ("heimdall-financas", "Heimdall Finanças", False)}

AS_LISTAR_PASTA = r'''-- heimdall:listar-pasta
on run argv
	set pn to item 1 of argv
	set raiz to item 2 of argv
	set out to ""
	tell application "Notes"
		if raiz is "" then
			set pastas to (every folder whose name is pn)
		else
			set pastas to {}
			repeat with r in (every folder whose name is raiz)
				try
					set pastas to pastas & (every folder of r whose name is pn)
				end try
			end repeat
		end if
		repeat with f in pastas
			repeat with n in (every note of f)
				set out to out & (id of n) & tab & (name of n) & linefeed
			end repeat
		end repeat
	end tell
	return out
end run
'''
AS_APAGAR_NOTA = r'''-- heimdall:apagar-nota
on run argv
	tell application "Notes"
		delete (first note whose id is (item 1 of argv))
	end tell
	return "ok"
end run
'''


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


def _titulo_md(texto: str, padrao: str) -> str:
    for ln in texto.splitlines():
        if ln.startswith("# "):
            return ln[2:].strip()[:av.MAX_TITULO] or padrao
    return padrao


def _tira_frontmatter(texto: str) -> str:
    if texto.startswith("---\n"):
        fim = texto.find("\n---", 4)
        if fim > 0:
            return texto[fim + 4:].lstrip("\n")
    return texto


def migrar(cofre: Path, osa=None, raiz: str = "Heimdall-ai", simular: bool = False, avisos_de=av.do_servico, log=print) -> dict:
    """Devolve {"importados", "apagados_notas", "apagados_arquivos", "erros": [...]}. `osa(script, *args)` roda o AppleScript (None = só o cofre)."""
    res = {"importados": 0, "apagados_notas": 0, "apagados_arquivos": 0, "erros": []}
    itens = []   # (servico, origem, titulo, texto, criado)
    arquivos = []   # arquivos do cofre a apagar depois da conferência
    notas_apple = []   # ids das notas do app Notas a apagar
    for serv, (pasta, pasta_notas, na_raiz) in ORIGENS.items():
        ja = {_norm(a["titulo"]) for a in avisos_de(serv).listar(av.MAX_AVISOS)}   # já nos avisos (de uma rodada anterior): não importa de novo
        d = Path(cofre) / pasta
        if d.is_dir():
            for f in sorted(d.glob("*.md")):
                try:
                    bruto = f.read_text(encoding="utf-8", errors="replace")
                except OSError as ex:
                    res["erros"].append(f"não li {f.name}: {ex}")
                    continue
                titulo = _titulo_md(bruto, f.stem)
                criado = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                itens.append((serv, f"cofre:{serv}:{f.name}", titulo, _tira_frontmatter(bruto), criado))
                ja.add(_norm(titulo))
                arquivos += [f] + [a for a in (d / "audio").glob(f.stem + ".*")] if (d / "audio").is_dir() else [f]
        if osa:
            try:
                saida = osa(AS_LISTAR_PASTA, pasta_notas, raiz if na_raiz else "")
            except Exception as ex:  # noqa: BLE001
                res["erros"].append(f"não consegui listar a pasta {pasta_notas} no app Notas: {str(ex)[:150]}")
                saida = ""
            for ln in saida.splitlines():
                nid, _, titulo = ln.partition("\t")
                if not nid:
                    continue
                notas_apple.append((serv, nid, titulo))
                if _norm(titulo) in ja:
                    continue   # é a mesma nota que o cofre já tem
                try:
                    corpo = osa(__import__("heimdall_agente").AS_LER, nid)
                except Exception as ex:  # noqa: BLE001
                    res["erros"].append(f"não li a nota {titulo[:40]}: {str(ex)[:120]}")
                    notas_apple.pop()
                    continue
                _, _, texto = corpo.partition("\n<<<CORPO>>>\n")
                itens.append((serv, f"notas:{nid}", titulo.strip() or "Nota", texto, ""))
    log(f"Encontrei {len(itens)} item(ns) para trazer e {len(notas_apple)} nota(s) no app Notas.")
    if simular:
        for it in itens:
            log(f"  traria para {av.SERVICOS[it[0]]}: {it[2][:60]}")
        res["importados"] = len(itens)
        return res
    for serv, origem, titulo, texto, criado in itens:
        try:
            avisos_de(serv).gravar(titulo, texto, criado=criado, origem=origem)
            res["importados"] += 1
        except Exception as ex:  # noqa: BLE001
            res["erros"].append(f"não importei {titulo[:40]}: {str(ex)[:120]}")
    faltam = [it[2] for it in itens if not avisos_de(it[0]).tem_origem(it[1])]
    if faltam or res["erros"]:
        res["erros"].append("conferência falhou: nada foi apagado" + (f" (faltam: {', '.join(x[:30] for x in faltam[:5])})" if faltam else ""))
        return res
    for serv, nid, titulo in notas_apple:
        try:
            osa(AS_APAGAR_NOTA, nid)
            res["apagados_notas"] += 1
        except Exception as ex:  # noqa: BLE001
            res["erros"].append(f"não apaguei a nota {titulo[:40]}: {str(ex)[:120]}")
    if res["erros"]:
        res["erros"].append("como houve erro ao apagar no app Notas, mantive as cópias do cofre; rode de novo depois de resolver")
        return res
    for f in arquivos:
        try:
            f.unlink()
            res["apagados_arquivos"] += 1
        except OSError as ex:
            res["erros"].append(f"não apaguei {f.name}: {ex}")
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="Traz as notas de saúde e finanças para a aba Avisos e apaga as originais")
    ap.add_argument("--executar", action="store_true", help="importa, confere e apaga (sem isto, só mostra o que seria feito)")
    a = ap.parse_args()
    import heimdall_agente as ag
    cofre = ag.VAULT

    def osa(script, *args):
        with ag._lock:
            return ag.osascript(script, *args)
    r = migrar(cofre, osa if sys.platform == "darwin" else None, ag.RAIZ_ANTIGA, not a.executar)
    print(f"Importados: {r['importados']}. Notas apagadas no app Notas: {r['apagados_notas']}. Arquivos apagados do cofre: {r['apagados_arquivos']}.")
    for e in r["erros"]:
        print("Aviso:", e)
    return 1 if r["erros"] else 0


if __name__ == "__main__":
    sys.exit(main())
