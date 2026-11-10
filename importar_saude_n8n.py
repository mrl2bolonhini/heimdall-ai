#!/usr/bin/env python3
"""Copia para o banco (banco/heimdall.db) o histórico de saúde que já está guardado dentro do n8n.

Rode uma vez, no Mac, com o Docker aberto e o n8n no ar:
    python importar_saude_n8n.py
Pode rodar de novo à vontade: grava pela chave (dia, métrica) e não duplica. Só lê o n8n (cópia temporária do arquivo dele).
"""
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import heimdall_banco as banco

CONTAINER = "n8n"
ID_FLUXO = "hdSaude000000001"
CAMINHO = "/home/node/.n8n/database.sqlite"
UNIDADES = {"passos": "count", "energia": "kcal", "fc_repouso": "bpm", "hrv": "ms", "resp": "rpm", "spo2": "%", "glicose": "mg/dL",
            "glicose_min": "mg/dL", "sono_total": "min", "sono_profundo": "min", "sono_rem": "min", "sono_cama": "min"}


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="heimdall-n8n-"))
    try:
        for sufixo, obrigatorio in (("", True), ("-wal", False), ("-shm", False)):
            r = subprocess.run(["docker", "cp", f"{CONTAINER}:{CAMINHO}{sufixo}", str(tmp / f"n8n.db{sufixo}")], capture_output=True, text=True)
            if r.returncode != 0 and obrigatorio:
                print("Não consegui copiar o arquivo do n8n. O Docker está aberto e o contêiner 'n8n' no ar?\n" + r.stderr.strip()[:300])
                return 1
        con = sqlite3.connect(tmp / "n8n.db")
        try:
            linha = con.execute("SELECT staticData FROM workflow_entity WHERE id=?", (ID_FLUXO,)).fetchone()
        finally:
            con.close()
        if not linha or not linha[0]:
            print("O fluxo de saúde ainda não guardou nenhum dado.")
            return 1
        sd = json.loads(linha[0]).get("global", {}).get("saude", {})
        dias, un = sd.get("dias", {}), sd.get("un", {})
        registros = []
        for dia, mets in dias.items():
            for k, v in mets.items():
                if isinstance(v, (int, float)):
                    registros.append({"dia": dia, "metrica": k, "valor": v, "unidade": UNIDADES.get(k) or un.get(k, "")})
        banco.iniciar()
        r = banco.gravar("saude_diaria", registros)
        print(f"Dias encontrados no n8n: {len(dias)}. Linhas gravadas no banco: {r['gravados']} (recusadas: {r['recusados']}).")
        print(json.dumps(banco.resumo()["saude_diaria"], ensure_ascii=False))
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
