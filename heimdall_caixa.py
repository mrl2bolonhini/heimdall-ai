#!/usr/bin/env python3
"""Cliente da caixa de correio na Cloudflare (Worker heimdall-caixa): o Mac busca o que os celulares deixaram e deixa o que eles devem aplicar.

Interruptor: HEIMDALL_CAIXA=1 no .env liga; qualquer outro valor desliga e o Heimdall volta a depender só do agente do Mac.
Chaves no .env: HEIMDALL_CAIXA_URL (padrão abaixo), HEIMDALL_CAIXA_TOKEN (token de dono, criado por `start`), CLOUDFLARE_API_TOKEN (só para `start`).
Antes de apagar qualquer item da caixa, o Mac grava uma cópia em db/mailbox/<pessoa>/ (permissão só do dono): nada se perde.

    python3 heimdall_caixa.py status          estado (ligada ou não) e se o Worker responde
    python3 heimdall_caixa.py start           cria o token de dono (prova acesso com a chave da Cloudflare) e o grava no .env
    python3 heimdall_caixa.py add NOME        cria o token de uma pessoa (a-z, 0-9, hífen); o token vai para a área de transferência
                                              (o seu celular é a pessoa 'eu', ou o nome em HEIMDALL_CAIXA_MEU_NOME: a saúde dele entra no banco de saúde)
    python3 heimdall_caixa.py remove NOME     revoga o token de uma pessoa
    python3 heimdall_caixa.py pull            busca as entradas, grava a cópia local e apaga da caixa
"""
import json
import heimdall_pastas
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
URL_PADRAO = "https://heimdall-caixa.mbolonhinic.workers.dev"
USER_AGENT = "heimdall-ai/1.0"
CHAVES = ("HEIMDALL_CAIXA", "HEIMDALL_CAIXA_URL", "HEIMDALL_CAIXA_TOKEN", "HEIMDALL_CAIXA_MEU_NOME", "CLOUDFLARE_API_TOKEN")
PASTA = heimdall_pastas.db_mailbox(AQUI)


def _env() -> dict:
    """Valores do .env lidos na hora (o interruptor vale sem reiniciar); o ambiente do processo tem prioridade."""
    out = {}
    try:
        for ln in (AQUI / ".env").read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln.startswith("export "):
                ln = ln[7:]
            k, _, v = ln.partition("=")
            if k.strip() in CHAVES:
                out[k.strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    for k in CHAVES:
        if os.environ.get(k):
            out[k] = os.environ[k]
    return out


def ativa(env=None) -> bool:
    env = _env() if env is None else env
    return env.get("HEIMDALL_CAIXA") == "1" and bool(env.get("HEIMDALL_CAIXA_TOKEN"))


def pedido(metodo, rota, corpo=None, token=None, extra=None, env=None, abrir=None, timeout=30):
    """Chama o Worker. Devolve o JSON; levanta RuntimeError com mensagem clara em qualquer falha."""
    env = _env() if env is None else env
    abrir = abrir or urllib.request.urlopen
    url = env.get("HEIMDALL_CAIXA_URL", URL_PADRAO).rstrip("/") + rota
    cab = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
    if token:
        cab["Authorization"] = "Bearer " + token
    cab.update(extra or {})
    dados = None if corpo is None else json.dumps(corpo).encode()
    try:
        with abrir(urllib.request.Request(url, data=dados, headers=cab, method=metodo), timeout=timeout) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode()).get("erro", "")
        except Exception:  # noqa: BLE001
            msg = ""
        raise RuntimeError(f"a caixa respondeu HTTP {e.code}" + (f": {msg}" if msg else "")) from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise RuntimeError(f"sem resposta da caixa ({type(e).__name__})") from None


def _dono(env):
    t = env.get("HEIMDALL_CAIXA_TOKEN", "")
    if not t:
        raise RuntimeError("falta o token de dono: rode studio mailbox start")
    return t


def iniciar(env=None, abrir=None, gravar=None) -> str:
    env = _env() if env is None else env
    cf = env.get("CLOUDFLARE_API_TOKEN", "")
    if not cf:
        raise RuntimeError("falta a chave da Cloudflare: rode studio cloudflare")
    r = pedido("POST", "/v1/iniciar", extra={"x-cf-token": cf}, env=env, abrir=abrir)
    token = r.get("token", "")
    if not token:
        raise RuntimeError("a caixa não devolveu o token")
    if gravar is None:
        import heimdall_lab
        gravar = heimdall_lab.env_gravar
    gravar({"HEIMDALL_CAIXA_TOKEN": token})
    return token


def criar_pessoa(nome, env=None, abrir=None) -> str:
    env = _env() if env is None else env
    return pedido("POST", "/v1/tokens", {"usuario": nome}, token=_dono(env), env=env, abrir=abrir)["token"]


def revogar_pessoa(nome, env=None, abrir=None) -> int:
    env = _env() if env is None else env
    return pedido("DELETE", f"/v1/tokens/{nome}", token=_dono(env), env=env, abrir=abrir).get("revogados", 0)


def deixar_para(usuario, tipo, dados, env=None, abrir=None) -> str:
    """Deixa na saída da pessoa um item (lembrete ou evento) para o celular dela aplicar."""
    env = _env() if env is None else env
    return pedido("POST", "/v1/saida", {"usuario": usuario, "tipo": tipo, "dados": dados}, token=_dono(env), env=env, abrir=abrir)["id"]


def puxar(env=None, abrir=None, pasta=None, tratar=None) -> dict:
    """Busca as entradas, grava a cópia local e só então apaga da caixa. `tratar(item)` roda depois da cópia (fase seguinte: importar saúde, notas...).
    Devolve {'recebidos', 'apagados', 'falhas'}."""
    env = _env() if env is None else env
    pasta = Path(pasta or PASTA)
    tok = _dono(env)
    itens = pedido("GET", "/v1/entrada", token=tok, env=env, abrir=abrir, timeout=60).get("itens", [])
    res = {"recebidos": len(itens), "apagados": 0, "falhas": 0}
    for it in itens:
        try:
            dest = pasta / it["usuario"]
            dest.mkdir(parents=True, exist_ok=True)
            os.chmod(dest, 0o700)
            arq = dest / f"{it['id']}.json"
            arq.write_text(json.dumps(it, ensure_ascii=False), encoding="utf-8")
            os.chmod(arq, 0o600)
            if tratar:
                tratar(it)
            pedido("DELETE", f"/v1/entrada/{it['usuario']}/{it['id']}", token=tok, env=env, abrir=abrir)
            res["apagados"] += 1
        except (OSError, RuntimeError, KeyError):
            res["falhas"] += 1
    return res


def importar_saude(nome: str, dados, meu_nome: str = "") -> dict:
    """Grava a saúde de uma pessoa no banco dela (db/people/<nome>/, ou o banco de sempre se for o dono): treinos, ECG, frequência por hora, eventos
    (heimdall_saude) e métricas diárias (heimdall_saude_diaria). Aceita o formato do Atalho (heimdall_atalhos) e o do Health Auto Export."""
    import heimdall_atalhos
    import heimdall_banco
    import heimdall_saude
    import heimdall_saude_diaria
    payload = heimdall_atalhos.para_hae(dados) if heimdall_atalhos.e_atalho(dados) else dados
    with heimdall_banco.pessoa(nome, meu_nome):
        res = heimdall_saude.processar_hae(payload)
        res["diarias"] = heimdall_saude_diaria.gravar(payload)
    return res


def tratar_padrao(item: dict, env=None, importar=None) -> None:
    """Importa o que já tem destino no Heimdall: saúde de cada pessoa, no banco dela (o do dono é o banco de sempre).
    Outros tipos (notas...) ficam só na cópia local até existir o destino deles."""
    env = _env() if env is None else env
    if item.get("tipo") == "saude":
        (importar or importar_saude)(item.get("usuario", ""), item.get("dados"), env.get("HEIMDALL_CAIXA_MEU_NOME", "eu"))


def _copiar(texto: str) -> bool:
    try:
        subprocess.run(["pbcopy"], input=texto.encode(), check=True, timeout=5)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def main(argv=None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    cmd = a[0] if a else "status"
    env = _env()
    try:
        if cmd == "status":
            print("Caixa de correio: " + ("LIGADA." if ativa(env) else "DESLIGADA (HEIMDALL_CAIXA=1 liga, depois de rodar studio mailbox start)."))
            if env.get("HEIMDALL_CAIXA_TOKEN"):
                try:
                    n = len(pedido("GET", "/v1/entrada", token=env["HEIMDALL_CAIXA_TOKEN"], env=env).get("itens", []))
                    print(f"A caixa responde. Itens esperando o Mac: {n}.")
                except RuntimeError as e:
                    print(f"Problema: {e}.")
                    return 1
            else:
                print("Ainda sem token de dono. Rode: studio mailbox start")
        elif cmd == "start":
            iniciar(env)
            print("Token de dono criado e gravado no .env. Para ligar: studio env --set HEIMDALL_CAIXA 1")
        elif cmd == "add" and len(a) == 2:
            t = criar_pessoa(a[1], env)
            if _copiar(t):
                print(f"Token de {a[1]} criado e copiado para a área de transferência. Cole-o só no aparelho dessa pessoa (ele não aparece de novo).")
            else:
                print(f"Token de {a[1]} (guarde agora, não aparece de novo): {t}")
        elif cmd == "remove" and len(a) == 2:
            n = revogar_pessoa(a[1], env)
            print(f"Pessoa {a[1]}: {n} token(s) revogado(s).")
        elif cmd == "pull":
            if not ativa(env):
                print("Caixa desligada: nada a fazer. Para ligar: studio env --set HEIMDALL_CAIXA 1")
                return 0
            r = puxar(env, tratar=lambda it: tratar_padrao(it, env))
            print(f"Recebidos {r['recebidos']}, apagados da caixa {r['apagados']}, falhas {r['falhas']}. Cópias em db/mailbox/.")
            return 1 if r["falhas"] else 0
        else:
            print(__doc__)
            return 2
    except RuntimeError as e:
        print(f"Erro: {e}.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
