"""Testa a análise de saúde com dados FICTÍCIOS de um dia, pelo LiteLLM (porta 9000).
As regras (em Python) decidem o que é relevante e o modelo só redige; assim ele não trata variação pequena como alerta.
Uso, na pasta do projeto, com o sistema no ar:
    python3 teste_saude.py                       # modelo medgemma
    python3 teste_saude.py qwen3-vl-instruct     # compara com outro modelo do litellm_config.yaml
    python3 teste_saude.py medgemma --bruto      # prompt antigo, sem as regras (para comparar)"""
import json, re, sys, time, urllib.request
from pathlib import Path

def chave():
    arq = Path(__file__).resolve().parent / ".env"
    for linha in arq.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*(?:export\s+)?LITELLM_MASTER_KEY=['\"]?([^'\"\s]+)", linha)
        if m:
            return m.group(1)
    sys.exit("LITELLM_MASTER_KEY não encontrada no .env")

# (nome, unidade, valor de hoje, média de 30 dias, sentido ruim: -1 = cair é ruim, +1 = subir é ruim, 0 = nunca alerta isolado)
DIA = [
    ("Sono total", "min", 320, 425, -1), ("Sono profundo", "min", 48, 85, -1), ("Sono REM", "min", 55, 90, -1),
    ("Frequência cardíaca em repouso", "bpm", 66, 58, +1), ("Variabilidade cardíaca (HRV)", "ms", 29, 46, -1),
    ("Passos", "", 3100, 7800, -1), ("Energia ativa", "kcal", 140, 410, -1),
    ("Oxigênio no sangue", "%", 96, 97, -1), ("Frequência respiratória no sono", "rpm", 16.5, 14.8, +1),
]

def classificar(nome, hoje, media, sentido):
    d = hoje - media
    pct = 100 * d / media if media else 0
    if nome == "Oxigênio no sangue":              # limite clínico, não percentual
        return "forte" if hoje < 92 else "moderada" if hoje < 94 or d <= -3 else "normal", pct
    if nome == "Frequência cardíaca em repouso":  # bpm absolutos
        return ("forte" if d >= 8 else "moderada" if d >= 5 else "normal"), pct
    if nome == "Frequência respiratória no sono":
        return ("forte" if d >= 2.5 else "moderada" if d >= 1.5 else "normal"), pct
    if nome in ("Passos", "Energia ativa"):       # atividade: contexto, nunca sinal de doença sozinha
        return ("moderada" if pct <= -40 else "normal"), pct
    ruim = -pct if sentido < 0 else pct
    return ("forte" if ruim >= 30 else "moderada" if ruim >= 20 else "normal"), pct

linhas_rel, linhas_ok, fortes = [], [], 0
for nome, un, hoje, media, s in DIA:
    nivel, pct = classificar(nome, hoje, media, s)
    txt = "%s: hoje %s %s, média %s (%+.0f%%)" % (nome, hoje, un, media, pct)
    if nivel == "normal":
        linhas_ok.append(txt)
    else:
        linhas_rel.append("%s [%s]" % (txt, "MUITO RELEVANTE" if nivel == "forte" else "relevante"))
        if nome in ("Sono total", "Variabilidade cardíaca (HRV)", "Frequência cardíaca em repouso", "Frequência respiratória no sono"):
            fortes += 1
padrao = ("%d dos 4 sinais de recuperação (sono total, variabilidade, pulso em repouso, respiração no sono) pioraram juntos." % fortes if fortes >= 3
          else "Há sinais isolados, sem um padrão claro de recuperação ruim." if linhas_rel else "Nada saiu do esperado.")

if "--bruto" in sys.argv:
    PROMPT = "Analise em português estes dados de saúde fictícios e dê recomendações:\n" + "\n".join("%s: %s %s (média %s)" % (n, h, u, m) for n, u, h, m, _ in DIA)
else:
    PROMPT = ("Você escreve o resumo diário de saúde de um adulto, em português do Brasil. O texto vai ser lido por um leitor de tela: "
              "só parágrafos curtos, sem listas, sem negrito, sem tabelas, sem símbolos.\n\n"
              "REGRAS: as classificações abaixo já foram decididas e você não as discute. Fale só do que está em RELEVANTE. "
              "Do que está em DENTRO DO NORMAL, diga numa frase que está normal. Não trate variação pequena como alerta. "
              "Evite 'pode ser' e 'talvez': escolha a explicação mais provável e uma menos provável, e diga qual é qual. "
              "Não diagnostique. Escreva exatamente quatro parágrafos curtos: (1) o que mudou, em uma ou duas frases; "
              "(2) a explicação mais provável para o conjunto e uma alternativa; (3) duas ações concretas para hoje, com horário ou quantidade; "
              "(4) o que observar nas próximas 48 horas e em que caso procurar um médico, com um critério claro (por exemplo febre acima de 37,8, falta de ar ou dor no peito).\n\n"
              "RELEVANTE:\n" + "\n".join(linhas_rel) + "\n\nDENTRO DO NORMAL:\n" + "\n".join(linhas_ok) + "\n\nPADRÃO GERAL: " + padrao)

modelo = next((a for a in sys.argv[1:] if not a.startswith("--")), "medgemma")
corpo = json.dumps({"model": modelo, "messages": [{"role": "user", "content": PROMPT}], "max_tokens": 700, "temperature": 0.2}).encode()
req = urllib.request.Request("http://localhost:9000/v1/chat/completions", data=corpo, headers={"Authorization": "Bearer " + chave(), "Content-Type": "application/json"})
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.load(r)
except Exception as e:  # noqa: BLE001
    sys.exit("falhou: %s" % str(e)[:300])
print("Modelo:", modelo)
print(d["choices"][0]["message"]["content"].strip())
print("\n[tempo: %.0f s | tokens: %s]" % (time.time() - t0, d.get("usage", {}).get("total_tokens")))
