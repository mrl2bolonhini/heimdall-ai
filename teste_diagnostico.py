#!/usr/bin/env python3
"""Teste do diagnóstico de desempenho (heimdall perf): análise dos textos do macOS, sem depender do Mac."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diagnostico as d  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        if detalhe:
            print("     " + str(detalhe)[:300])


vm = d.parse_vm_stat('Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free:                               1000.\nPages active:                            50000.\nPages wired down:                        30000.\nPages occupied by compressor:            20000.\n')
confere("vm_stat: tamanho de página e categorias", vm.get("pages active") == 50000 * 16384 and vm.get("pages occupied by compressor") == 20000 * 16384, vm)
sw = d.parse_swap("total = 3072.00M  used = 2012.50M  free = 1059.50M  (encrypted)")
confere("swap: lê usado e total", abs(sw["used"] - 2012.5 * 1024 ** 2) < 1 and abs(sw["total"] - 3072 * 1024 ** 2) < 1, sw)
confere("nome do processo: aplicativo", d.nome_do_processo("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome Helper") == "Google Chrome")
confere("nome do processo: script Python sem argumentos", d.nome_do_processo("/opt/homebrew/bin/python3", "python3 /x/heimdall_finance.py --senha SEGREDO") == "heimdall_finance.py")
ps = "1 1000 5,0 /Applications/Foo.app/Contents/MacOS/Foo\n2 2000 10,0 /Applications/Foo.app/Contents/MacOS/Foo Helper\n3 500 1,0 /usr/bin/ssh\n"
ag = {a["nome"]: a for a in d.parse_ps(ps)}
confere("ps agrega por aplicativo", ag["Foo"]["n"] == 2 and ag["Foo"]["mem"] == 3000 * 1024 and ag["ssh"]["n"] == 1, ag)
confere("ollama ps lista os modelos", d.parse_ollama_ps("NAME ID SIZE PROCESSOR UNTIL\nllama3:8b  abc  5.0 GB  100% GPU  4 minutes from now\n") == ["llama3:8b | abc | 5.0 GB | 100% GPU | 4 minutes from now"])
dk = d.parse_docker_stats("n8n|3.2%|512MiB / 4GiB\nqdrant|0.1%|1.5GiB / 4GiB\n")
confere("docker stats: nome, cpu e memória", dk[0] == {"nome": "n8n", "cpu": "3.2%", "mem": "512MiB"} and d._mem_texto_para_bytes("1.5GiB") == 1.5 * 1024 ** 3, dk)
achados = []
d.disco(achados)
confere("o diagnóstico completo roda sem erro mesmo sem os comandos do Mac", d.main(["--topo", "3"]) == 0)
print()
print("FALHAS: " + str(falhas))
sys.exit(1 if falhas else 0)
