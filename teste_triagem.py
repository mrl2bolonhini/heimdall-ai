#!/usr/bin/env python3
"""Testa a triagem obrigatória (heimdall_triagem.py).

    python3 teste_triagem.py          regras de insistência, com uma simulação do app Lembretes e do Bark (qualquer máquina)
    python3 teste_triagem.py --mac    confere os AppleScripts de verdade no Mac: cria um lembrete de teste na lista
                                      "Heimdall: Triagem" e o lê de volta (não envia Bark; autorize o app Lembretes se pedir)

Usa um banco temporário; não toca no seu banco.
"""
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

os.environ["HEIMDALL_DB_DIR"] = tempfile.mkdtemp(prefix="heimdall-triagem-")
import heimdall_banco as banco  # noqa: E402
import heimdall_triagem as T  # noqa: E402

falhas = 0


def ok(cond, msg):
    global falhas
    print(("ok   " if cond else "FALHA ") + msg)
    if not cond:
        falhas += 1


def osascript_real(script, *args):
    with tempfile.NamedTemporaryFile("w", suffix=".applescript", delete=False, encoding="utf-8") as f:
        f.write(script)
        caminho = f.name
    try:
        r = subprocess.run(["osascript", caminho, *args], capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise RuntimeError("o macOS não respondeu em 60 s: provavelmente há um pedido de permissão aberto na tela do Mac, esperando você permitir "
                           "o controle do app Lembretes") from None
    finally:
        os.unlink(caminho)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "osascript falhou").strip()[:400])
    return r.stdout.rstrip("\n")


if "--mac" in sys.argv:
    print("1. Criando um lembrete de teste na lista \"%s\" (autorize o app Lembretes, se pedir)..." % T.NOME_LISTA)
    origem = "teste-mac-%d" % int(datetime.now().timestamp())
    try:
        r = T.criar({"id": origem, "titulo": "Teste de triagem: pode concluir", "resumo": "Lembrete de teste criado por teste_triagem.py.",
                     "nivel": "medio", "fonte": "teste"}, osascript_real)
    except RuntimeError as e:
        print("FALHA", e)
        print("Quando você permitir no Mac (ou o app Lembretes voltar a responder), rode este teste de novo.")
        sys.exit(1)
    ok(r["lembrete"] == "criado", "lembrete criado: %s" % r)
    r2 = T.criar({"id": origem, "titulo": "Teste de triagem: pode concluir", "nivel": "medio"}, osascript_real)
    ok(r2["lembrete"] == "ja_existe", "criar de novo não duplica: %s" % r2["lembrete"])
    print("2. Lendo a lista de volta...")
    existe, itens = T.ler_lembretes(osascript_real)
    ok(existe, "a lista existe")
    mio = itens.get(r["id"])
    ok(mio is not None, "o lembrete de teste aparece na leitura")
    if mio:
        ok(not mio["feito"], "está pendente")
        ok(mio["prioridade"] == T.PRIORIDADE_INICIAL["medio"], "prioridade inicial %s" % mio["prioridade"])
        ok(mio["vence_em"] is not None and mio["vence_em"] < 120, "horário de vencimento lido (%s s)" % mio["vence_em"])
        ok("Teste de triagem" in mio["nome"], "nome lido")
    print("3. Rodando um ciclo sem enviar Bark...")
    enviados = []
    res = T.ciclo(osascript_real, enviar=lambda p: enviados.append(p) or True)
    print("   ", res)
    ok(res["lista_existe"], "ciclo enxerga a lista")
    print("\nPronto. Abra o app Lembretes, lista \"%s\", e conclua o lembrete de teste. Rode de novo daqui a pouco para ver a conclusão lida." % T.NOME_LISTA)
    sys.exit(1 if falhas else 0)

# ------------------------------------------------------------------------------------------------
# Simulação do app Lembretes
# ------------------------------------------------------------------------------------------------
BASE = datetime(2026, 11, 11, 15, 0, tzinfo=timezone.utc)  # 12h em São Paulo
NOW = BASE
T._agora = lambda: NOW   # relógio simulado
store = {}   # tid -> dict(nome, prioridade, vence, feito, feito_em)
lista_existe = [True]


def relogio(h=0, m=0):
    """Horário simulado, contado a partir do início do cenário (BASE)."""
    return BASE + timedelta(hours=h, minutes=m)


def osa(script, *args):
    if script is T.AS_CRIAR:
        tid, tit, corpo, prio, _lista = args
        if tid in store:
            return "ja_existe"
        store[tid] = {"nome": tit, "prioridade": int(prio), "vence": NOW + timedelta(seconds=60), "feito": False, "feito_em": None}
        return "criado"
    if script is T.AS_LER:
        if not lista_existe[0]:
            return "lista:ausente"
        saida = "lista:ok\n"
        for tid, i in store.items():
            vence = "" if i["vence"] is None else str(int((i["vence"] - NOW).total_seconds()))
            fe = "" if i["feito_em"] is None else str(int((i["feito_em"] - NOW).total_seconds()))
            saida += "\t".join([tid, "1" if i["feito"] else "0", str(i["prioridade"]), vence, fe, i["nome"]]) + "\n"
        return saida.rstrip("\n")
    raise AssertionError("script inesperado")


enviados = []
bark_ok = [True]


def bark(p):
    if bark_ok[0]:
        enviados.append(p)
    return bark_ok[0]


def novo(origem, nivel="alto", fonte="email", titulo="Teste"):
    r = T.criar({"id": origem, "titulo": titulo, "resumo": "Resumo de " + origem, "nivel": nivel, "fonte": fonte}, osa)
    return r["id"]


def rodar(h=0, m=0):
    global NOW
    NOW = relogio(h, m)
    antes = len(enviados)
    res = T.ciclo(osa, bark, NOW)
    return res, enviados[antes:]


def linha(tid):
    con = banco.conectar(somente_leitura=True)
    try:
        return dict(con.execute("SELECT * FROM triagem WHERE id=?", (tid,)).fetchone())
    finally:
        con.close()


banco.iniciar()

print("== Criar")
tid = novo("a1", "alto")
ok(T.criar({"id": "a1", "titulo": "Teste", "nivel": "alto"}, osa)["lembrete"] == "ja_existe", "criar de novo não duplica o lembrete")
ok(banco.resumo()["triagem"]["linhas"] == 1, "uma só linha no banco")
ok(store[tid]["prioridade"] == 5, "prioridade inicial do nível alto é média (5)")
try:
    T.criar({"id": "", "titulo": ""}, osa)
    ok(False, "recusa pedido sem id e título")
except ValueError:
    ok(True, "recusa pedido sem id e título")

print("== Leitura do AppleScript (formato)")
txt = "lista:ok\nabc\t0\t5\t55\t\tTítulo\tcom tab\nxyz\t1\t1\t\t-3600\tFeito\n"
existe, it = T.ler_lembretes(lambda s, *a: txt)
ok(existe and it["abc"]["vence_em"] == 55 and it["abc"]["nome"] == "Título\tcom tab" and it["xyz"]["feito"] and it["xyz"]["feito_em"] == -3600, "interpreta as linhas")
ok(T.ler_lembretes(lambda s, *a: "lista:ausente")[0] is False, "lista ausente é reconhecida")

print("== Insistência de dia (12h): alto")
res, env = rodar(0, 1)
ok(len(env) == 1 and env[0]["level"] == "timeSensitive" and not env[0]["title"].startswith("CRÍTICO"), "primeiro aviso na hora, nível timeSensitive")
ok(env[0]["badge"] == 1 and env[0]["group"] == "triagem", "badge com o número de pendentes")
res, env = rodar(0, 16)
ok(len(env) == 0, "sem novo aviso 15 min depois")
res, env = rodar(2, 2)
ok(len(env) == 1 and linha(tid)["avisos"] == 2, "repete depois de 2 horas")

print("== À noite não toca")
store.clear()
banco_con = banco.conectar(); banco_con.execute("DELETE FROM triagem"); banco_con.commit(); banco_con.close()
BASE = NOW = datetime(2026, 11, 11, 4, 0, tzinfo=timezone.utc)
t2 = novo("noite", "alto")
res, env = rodar(0, 1)
ok(len(env) == 0, "item alto criado à 1h não toca de madrugada")
res, env = rodar(5, 5)   # 6h06 local... ainda cedo
ok(len(env) == 0, "6h06 ainda não toca")
res, env = rodar(6, 5)   # 7h06 local
ok(len(env) == 1, "às 7h toca o primeiro aviso")

print("== Crítico fura o silêncio")
store.clear()
banco_con = banco.conectar(); banco_con.execute("DELETE FROM triagem"); banco_con.commit(); banco_con.close()
BASE = NOW = datetime(2026, 11, 11, 4, 0, tzinfo=timezone.utc)
t3 = novo("crit", "critico", titulo="Prazo hoje")
res, env = rodar(0, 1)
ok(len(env) == 1 and env[0]["level"] == "critical" and env[0]["title"].startswith("CRÍTICO") and env[0].get("volume") == 7, "primeiro aviso crítico sai à 1h, nível critical")
res, env = rodar(2, 1)   # 3h local
ok(len(env) == 0, "a repetição de madrugada espera")
res, env = rodar(6, 5)   # 7h06 local
ok(len(env) == 1 and env[0]["level"] == "critical", "às 7h a repetição crítica sai")

print("== Diário da Justiça escala depois de 24 h")
store.clear()
banco_con = banco.conectar(); banco_con.execute("DELETE FROM triagem"); banco_con.commit(); banco_con.close()
BASE = NOW = datetime(2026, 11, 11, 15, 0, tzinfo=timezone.utc)
t4 = novo("dj1", "alto", fonte="justica", titulo="TJSP intimação")
res, env = rodar(0, 1)
ok(env and env[0]["level"] == "timeSensitive", "no começo é aviso comum")
res, env = rodar(23, 0)
ok(env and env[0]["level"] == "timeSensitive", "com 23 h ainda é comum")
res, env = rodar(25, 0)   # 25 h depois: 16h local
ok(env and env[0]["level"] == "critical", "depois de 24 h sem ação vira crítico")

print("== Concluir dispensa")
res, env = rodar(25, 30)
store[t4]["feito"] = True
store[t4]["feito_em"] = NOW
res, env = rodar(27, 0)
ok(res["concluidas"] == 1 and linha(t4)["estado"] == "concluida" and not env, "concluído: registra e para de avisar")
ok(linha(t4)["decidido_em"] != "" and linha(t4)["prioridade_usuario"] == "media", "registra quando e a prioridade deixada (média)")
res, env = rodar(30, 0)
ok(not env and res["pendentes"] == 0, "depois de concluído, nada mais")

print("== Classificar muda a insistência")
store.clear()
banco_con = banco.conectar(); banco_con.execute("DELETE FROM triagem"); banco_con.commit(); banco_con.close()
BASE = NOW = datetime(2026, 11, 11, 13, 0, tzinfo=timezone.utc)
t5 = novo("baixa", "alto")
rodar(0, 1)
store[t5]["prioridade"] = 9   # usuário marca como baixa
res, env = rodar(2, 5)
ok(res["classificadas"] == 1 and linha(t5)["prioridade_usuario"] == "baixa", "registra a classificação como baixa")
ok(not env, "com prioridade baixa, 2 h depois não avisa")
res, env = rodar(8, 5)
ok(len(env) == 1, "com prioridade baixa, avisa 8 h depois")

print("== Baixar a prioridade de um crítico tira o furo do silêncio")
store.clear()
banco_con = banco.conectar(); banco_con.execute("DELETE FROM triagem"); banco_con.commit(); banco_con.close()
BASE = NOW = datetime(2026, 11, 11, 13, 0, tzinfo=timezone.utc)
t6 = novo("crit2", "critico")
res, env = rodar(0, 1)
ok(env and env[0]["level"] == "critical", "começa crítico")
store[t6]["prioridade"] = 9
res, env = rodar(9, 0)
ok(env and env[0]["level"] == "timeSensitive", "depois de rebaixado, o aviso é comum")

print("== Adiar")
store.clear()
banco_con = banco.conectar(); banco_con.execute("DELETE FROM triagem"); banco_con.commit(); banco_con.close()
BASE = NOW = datetime(2026, 11, 11, 13, 0, tzinfo=timezone.utc)
t7 = novo("adia", "alto")
rodar(0, 1)
store[t7]["vence"] = relogio(5, 0)   # +5 h
res, env = rodar(2, 5)
ok(res["adiadas"] == 1 and linha(t7)["adiado_ate"] != "" and not env, "adiado: registra e não avisa")
res, env = rodar(4, 0)
ok(not env, "ainda adiado 4 h depois")
res, env = rodar(5, 30)
ok(len(env) == 1 and linha(t7)["adiado_ate"] == "", "passado o horário, volta a avisar")

print("== Apagar o lembrete")
store.clear()
banco_con = banco.conectar(); banco_con.execute("DELETE FROM triagem"); banco_con.commit(); banco_con.close()
BASE = NOW = datetime(2026, 11, 11, 13, 0, tzinfo=timezone.utc)
t8 = novo("apaga", "alto")
del store[t8]
res, env = rodar(0, 5)
ok(res["descartadas"] == 0 and linha(t8)["estado"] == "pendente", "logo depois de criado não descarta (margem de 10 min)")
res, env = rodar(0, 30)
ok(res["descartadas"] == 1 and linha(t8)["estado"] == "descartada" and not env, "lembrete apagado vira descartado e não avisa")

print("== Falha do Bark e lista ausente")
store.clear()
banco_con = banco.conectar(); banco_con.execute("DELETE FROM triagem"); banco_con.commit(); banco_con.close()
BASE = NOW = datetime(2026, 11, 11, 13, 0, tzinfo=timezone.utc)
t9 = novo("bark", "alto")
bark_ok[0] = False
res, env = rodar(0, 1)
ok(res["falhas_aviso"] == 1 and linha(t9)["avisos"] == 0, "se o Bark falha, não conta como avisado")
bark_ok[0] = True
res, env = rodar(0, 16)
ok(len(env) == 1 and linha(t9)["avisos"] == 1, "no próximo ciclo tenta de novo")
lista_existe[0] = False
res, env = rodar(5, 0)
ok(res["lista_existe"] is False and linha(t9)["estado"] == "pendente" and res["descartadas"] == 0, "lista ausente: não descarta nem conclui nada")
lista_existe[0] = True

print("== App Lembretes sem resposta (permissão pendente no Mac)")
store.clear()
banco_con = banco.conectar(); banco_con.execute("DELETE FROM triagem"); banco_con.commit(); banco_con.close()
BASE = NOW = datetime(2026, 11, 11, 13, 0, tzinfo=timezone.utc)   # 10h local
funciona = [False]


def osa_travado(script, *args):
    if not funciona[0]:
        raise RuntimeError("o macOS não respondeu em 45 s (provável pedido de permissão aberto na tela do Mac)")
    return osa(script, *args)


try:
    T.criar({"id": "perm1", "titulo": "Sem permissão", "resumo": "Resumo", "nivel": "alto", "fonte": "justica"}, osa_travado)
    ok(False, "criar avisa que o lembrete não foi criado")
except RuntimeError as e:
    ok("registrado" in str(e), "criar avisa que o lembrete não foi criado, mas o item foi registrado")
tid_p = T.gerar_id("perm1")
ok(linha(tid_p)["lembrete"] == 0 and linha(tid_p)["estado"] == "pendente", "item fica no banco com lembrete = 0")
NOW = relogio(0, 1)
enviados.clear()
res = T.ciclo(osa_travado, bark, NOW)
ok(res["erro_lembretes"] != "" and len(enviados) == 1, "ciclo sem acesso ao app: o Bark avisa mesmo assim")
ok("autorização pendente" in enviados[0]["body"], "o aviso explica que falta a autorização no Mac")
NOW = relogio(2, 5)
res = T.ciclo(osa_travado, bark, NOW)
ok(len(enviados) == 2, "e continua insistindo a cada 2 horas")
funciona[0] = True
NOW = relogio(4, 10)
enviados.clear()
res = T.ciclo(osa_travado, bark, NOW)
ok(res["lembretes_criados"] == 1 and linha(tid_p)["lembrete"] == 1 and tid_p in store, "com o app de volta, o ciclo cria o lembrete que faltava")
ok(len(enviados) == 1 and "Abra o app Lembretes" in enviados[0]["body"], "e o aviso volta ao texto normal")
res = T.ciclo(osa_travado, bark, relogio(4, 25))
ok(res["lembretes_criados"] == 0 and res["pendentes"] == 1, "no ciclo seguinte, nada é criado de novo")

print("== Migração de um banco criado antes da coluna lembrete")
con = banco.conectar()
con.execute("DROP TABLE triagem")
con.execute("CREATE TABLE triagem (id TEXT PRIMARY KEY, criado TEXT NOT NULL, fonte TEXT NOT NULL DEFAULT '', nivel TEXT NOT NULL DEFAULT 'alto', "
            "titulo TEXT NOT NULL DEFAULT '', resumo TEXT NOT NULL DEFAULT '', estado TEXT NOT NULL DEFAULT 'pendente', "
            "prioridade_usuario TEXT NOT NULL DEFAULT '', decidido_em TEXT NOT NULL DEFAULT '', adiado_ate TEXT NOT NULL DEFAULT '', "
            "avisos INTEGER NOT NULL DEFAULT 0, ultimo_aviso TEXT NOT NULL DEFAULT '', atualizado TEXT NOT NULL)")
con.execute("INSERT INTO triagem (id, criado, titulo, atualizado) VALUES ('velho', '2026-11-10T10:00:00Z', 'Antigo', '2026-11-10T10:00:00Z')")
con.commit(); con.close()
banco.iniciar()
ok(linha("velho")["lembrete"] == 1, "a coluna é criada e as linhas antigas contam como já tendo lembrete")

print("== Estado")
e = T.estado()
ok(e["total"] >= 1 and isinstance(e["pendentes"], list), "estado devolve a lista")

print("\n%s" % ("Tudo certo." if not falhas else "%d falha(s)." % falhas))
sys.exit(1 if falhas else 0)
