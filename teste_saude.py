"""Testa o modelo de saúde (medgemma) com dados FICTÍCIOS de um dia, pelo LiteLLM (porta 9000).
Mede o tempo, a memória não é tocada além do que o Ollama já usa. Não envia nada seu: os números são inventados.
Uso, na pasta do projeto, com o sistema no ar: python3 teste_saude.py"""
import json, re, sys, time, urllib.request
from pathlib import Path

def chave():
    arq = Path(__file__).resolve().parent / ".env"
    for linha in arq.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*(?:export\s+)?LITELLM_MASTER_KEY=['\"]?([^'\"\s]+)", linha)
        if m:
            return m.group(1)
    sys.exit("LITELLM_MASTER_KEY não encontrada no .env")

RESUMO = """Dados fictícios de hoje (pessoa de 40 anos), comparados com a média dos últimos 30 dias:
- Sono: 5h20 (média 7h05). Sono profundo 48 min (média 1h25). REM 55 min (média 1h30). Acordou 4 vezes.
- Frequência cardíaca em repouso: 66 bpm (média 58).
- Variabilidade da frequência cardíaca (HRV): 29 ms (média 46).
- Passos: 3.100 (média 7.800). Energia ativa: 140 kcal (média 410).
- Oxigênio no sangue: 96% (média 97%).
- Frequência respiratória durante o sono: 16,5 (média 14,8).
"""
PROMPT = ("Você analisa dados de saúde de um relógio e do app Saúde. Responda em português do Brasil, em texto corrido e frases curtas, sem tabelas. "
          "Diga: 1) o que mudou em relação à média; 2) o que isso pode significar, sem diagnosticar; 3) duas sugestões práticas para hoje; "
          "4) quando procurar um médico. Seja honesto sobre o que os dados não permitem concluir.\n\n" + RESUMO)

corpo = json.dumps({"model": "medgemma", "messages": [{"role": "user", "content": PROMPT}], "max_tokens": 700, "temperature": 0.3}).encode()
req = urllib.request.Request("http://localhost:9000/v1/chat/completions", data=corpo, headers={"Authorization": "Bearer " + chave(), "Content-Type": "application/json"})
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.load(r)
except Exception as e:  # noqa: BLE001
    sys.exit("falhou: %s\nO modelo foi baixado (ollama pull medgemma:4b) e o LiteLLM reiniciado depois de atualizar o litellm_config.yaml?" % str(e)[:300])
print(d["choices"][0]["message"]["content"].strip())
print("\n[tempo: %.0f s | tokens: %s]" % (time.time() - t0, d.get("usage", {}).get("total_tokens")))
