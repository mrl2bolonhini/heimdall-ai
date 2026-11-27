#!/usr/bin/env python3
"""Testa a parte de dados do Studio Learn: banco próprio, pastas com categoria e tipo, sincronização e importação de documentos."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp())
os.environ["STUDIO_DB_DIR"] = str(TMP / "db")
os.environ["STUDIO_KNOWLEDGE_DIR"] = str(TMP / "knowledge")
(TMP / "knowledge" / "aws").mkdir(parents=True)
(TMP / "knowledge" / "aws" / "guia.pdf").write_bytes(b"%PDF-1.4 x")
(TMP / "knowledge" / "esoterismo" / "tarot").mkdir(parents=True)
(TMP / "knowledge" / ".oculta").mkdir()

import heimdall_learn_dados as d  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


def erro(fn, *a, **k):
    try:
        fn(*a, **k)
    except d.ErroLearn as ex:
        return str(ex)
    return None


confere("o banco do Learn é separado do pessoal", d.caminho_banco() == TMP / "db" / "learn.db")
con = d.conectar()
confere("tipos iniciais cadastrados", {"Idiomas", "Programação", "Filosofia", "Medicina", "Exatas", "Humanas"} <= set(d.listar_tipos(con)))
confere("o arquivo do banco é só do dono", (d.caminho_banco().stat().st_mode & 0o777) == 0o600)

# sincronização das pastas que já existiam
n = d.sincronizar()
confere("cadastra as pastas existentes (aws, esoterismo e tarot) e ignora as ocultas", n == 3 and d.obter_pasta("aws") and erro(d.obter_pasta, ".oculta") is not None, n)
confere("pasta existente entra como aleatório, tipo Outro", d.obter_pasta("aws")["categoria"] == "aleatorio" and d.obter_pasta("aws")["tipo"] == "Outro")
confere("subpasta existente herda da pasta de cima", d.obter_pasta("esoterismo/tarot")["tipo"] == "Outro")
confere("sincronizar de novo não duplica", d.sincronizar() == 0)
confere("pasta existente marcada como origem existente", d.obter_pasta("aws")["origem"] == "existente")
d.atualizar_pasta("esoterismo", "aleatorio", "Esoterismo")
confere("atualizar categoria e tipo", d.obter_pasta("esoterismo")["tipo"] == "Esoterismo")

# criar pastas
p = d.criar_pasta("Inglês Básico", "sequencial", "Idiomas", "inglês")
confere("cria pasta no disco com nome simples", (TMP / "knowledge" / "ingles-basico").is_dir() and p["caminho"] == "ingles-basico" and p["nome"] == "Inglês Básico")
confere("a pasta criada é só do dono (0700)", ((TMP / "knowledge" / "ingles-basico").stat().st_mode & 0o777) == 0o700)
confere("idiomas exige o idioma de estudo", erro(d.criar_pasta, "Espanhol", "sequencial", "Idiomas", "") is not None)
confere("tipo novo é cadastrado ao criar a pasta", d.criar_pasta("Python", "sequencial", "Programação")["tipo"] == "Programação" and d.criar_pasta("Cálculo", "sequencial", "Exatas")["tipo"] == "Exatas")
d.criar_pasta("Direito Digital", "aleatorio", "Direito")
confere("tipo aberto: um tipo novo digitado passa a existir", "Direito" in d.listar_tipos())
confere("tipo existente com outra caixa não duplica", d.criar_tipo("direito") == "Direito" and d.listar_tipos().count("Direito") == 1)
sub = d.criar_pasta("Verbos", pai="ingles-basico")
confere("subpasta herda categoria, tipo e idioma", sub["categoria"] == "sequencial" and sub["tipo"] == "Idiomas" and sub["idioma"] == "inglês" and sub["caminho"] == "ingles-basico/verbos")
confere("recusa nome repetido", erro(d.criar_pasta, "Inglês Básico", "sequencial", "Idiomas", "inglês") is not None)
confere("recusa categoria inválida", erro(d.criar_pasta, "X Y", "qualquer", "Outro") is not None)
confere("recusa pasta de cima inexistente", erro(d.criar_pasta, "Abc", "aleatorio", "Outro", pai="nao-existe") is not None)
confere("sem categoria usa a sugerida pelo tipo (Outro: aleatório)", d.criar_pasta("Sem Cat", "", "Outro")["categoria"] == "aleatorio")
confere("tipo Programação sugere sequencial", d.criar_pasta("Linguagem Rust", "", "Programação")["categoria"] == "sequencial")
confere("recusa sem categoria, sem pai e sem tipo", erro(d.criar_pasta, "Sem Tipo", "", "") is not None)
confere("tipo novo usa o perfil genérico", d.tipos_perfis.perfil("Culinária")["categoria"] == "aleatorio" and d.tipos_perfis.perfil("idiomas")["pede_idioma"])
confere("recusa nome vazio ou sem letras", erro(d.criar_pasta, "!!", "aleatorio", "Outro") is not None)
confere("barra inicial nao vira caminho absoluto: /etc fica dentro de knowledge/", d.normalizar_caminho("/etc") == "etc" and d.pasta_no_disco("/etc") == (TMP / "knowledge" / "etc").resolve())
for ruim in ("../fora", "a/../../b", ".oculta", "a/./b"):
    confere(f"caminho suspeito recusado: {ruim}", erro(d.normalizar_caminho, ruim) is not None)
confere("profundidade máxima", erro(d.normalizar_caminho, "a/b/c/d/e/f") is not None)

# listagem
topo = {x["caminho"]: x for x in d.listar_pastas()}
confere("lista as pastas de nível de cima", {"aws", "esoterismo", "ingles-basico", "python"} <= set(topo) and "ingles-basico/verbos" not in topo)
confere("conta documentos e subpastas", topo["aws"]["documentos"] == 1 and topo["ingles-basico"]["subpastas"] == 1)
confere("lista as subpastas", [x["caminho"] for x in d.listar_pastas("ingles-basico")] == ["ingles-basico/verbos"])
(TMP / "knowledge" / "python").rename(TMP / "knowledge" / "python2")
confere("pasta que sumiu do disco não aparece", "python" not in {x["caminho"] for x in d.listar_pastas()})
(TMP / "knowledge" / "python2").rename(TMP / "knowledge" / "python")

# importar documentos
r = d.importar_documento("ingles-basico", "Lição 1.pdf", b"%PDF-1.4 conteudo")
confere("importa o documento", r["arquivo"] == "Lição 1.pdf" and (TMP / "knowledge" / "ingles-basico" / "Lição 1.pdf").read_bytes().startswith(b"%PDF"))
confere("o arquivo importado é só do dono (0600)", ((TMP / "knowledge" / "ingles-basico" / "Lição 1.pdf").stat().st_mode & 0o777) == 0o600)
r2 = d.importar_documento("ingles-basico", "Lição 1.pdf", b"%PDF-1.4 outro")
confere("nome repetido não sobrescreve", r2["arquivo"] == "Lição 1-2.pdf" and (TMP / "knowledge" / "ingles-basico" / "Lição 1.pdf").read_bytes().endswith(b"conteudo"))
confere("lista os documentos da pasta", [x["nome"] for x in d.listar_documentos("ingles-basico")] == ["Lição 1-2.pdf", "Lição 1.pdf"])
confere("registra os documentos no banco", d.resumo()["documentos"] == 2)
for nome in ("virus.exe", "../fuga.pdf", "sem_extensao", ".oculto.pdf", "a" * 200 + ".pdf"):
    r_ = erro(d.importar_documento, "ingles-basico", nome, b"x") if not nome.startswith("../") else None
    if nome.startswith("../"):
        feito = d.importar_documento("ingles-basico", nome, b"x")["arquivo"]
        confere("barra no nome vira só o nome do arquivo (sem sair da pasta)", feito == "fuga.pdf" and not (TMP / "knowledge" / "fuga.pdf").exists())
    else:
        confere(f"arquivo recusado: {nome[:20]}", r_ is not None)
confere("arquivo vazio recusado", erro(d.importar_documento, "ingles-basico", "vazio.pdf", b"") is not None)
os.environ["STUDIO_LEARN_MAX_MB"] = "1"
confere("arquivo acima do limite recusado", erro(d.importar_documento, "ingles-basico", "grande.pdf", b"x" * (1024 * 1024 + 1)) is not None)
confere("pasta não cadastrada recusa importação", erro(d.importar_documento, "aws/sub", "a.pdf", b"x") is not None and erro(d.importar_documento, "", "a.pdf", b"x") is not None)

# fuga por link simbólico
(TMP / "fora").mkdir()
os.symlink(TMP / "fora", TMP / "knowledge" / "link")
confere("link simbólico para fora de knowledge/ é recusado", erro(d.pasta_no_disco, "link") is not None)
d.sincronizar()
confere("sincronizar ignora link simbólico", d.obter_pasta("link") is None)
sys.exit(1 if falhas else 0)
