#!/usr/bin/env python3
"""Confere o app de barra de menus do Mac sem compilar (aqui não há Swift): arquivos, plist, chaves balanceadas, regras de segurança e do projeto.

    python3 tests/agent/teste_app_mac.py
A compilação de verdade acontece no Mac: studio app.
"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import plistlib
import re
import subprocess
import sys
from pathlib import Path

AQUI = RAIZ
falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


swift = (AQUI / "macapp" / "StudioLibre.swift").read_text(encoding="utf-8")
sh = (AQUI / "scripts/construir_app_mac.sh").read_text(encoding="utf-8")
pl = plistlib.loads((AQUI / "macapp" / "Info.plist").read_bytes())

confere("Info.plist: app normal (Dock e barra de menus do alto) e executável certo", "LSUIElement" not in pl and pl.get("CFBundleExecutable") == "StudioLibre" and pl.get("CFBundlePackageType") == "APPL")
confere("Swift: avisos nativos (UNUserNotificationCenter, pasta avisos_mac, interruptor nas Configurações)",
        "UNUserNotificationCenter" in swift and "avisos_mac" in swift and "avisosNoMac" in swift and "requestAuthorization" in swift)
sem_texto = re.sub(r"//[^\n]*", "", re.sub(r'"(?:[^"\\]|\\.)*"', '""', swift))
confere("Swift: chaves e parênteses balanceados", sem_texto.count("{") == sem_texto.count("}") and sem_texto.count("(") == sem_texto.count(")"))
confere("Swift: toda ação do menu tem método @objc", all(f"func {n}(" in swift for n in set(re.findall(r"#selector\((\w+)[(\)]", swift))))
confere("Swift: app normal desde o início, com o ícone na barra de estado", "setActivationPolicy(.regular)" in swift and ".accessory" not in swift and "statusItem" in swift)
confere("Swift: sites em janela própria (WKWebView), sem abrir o navegador", "WKWebView" in swift and "NSWorkspace.shared.open(" not in swift)
confere("Swift: nomes dos sites são os nomes reais em inglês", all(f'"{n}"' in swift for n in ("Controls", "Notes", "Learn", "News", "Health", "Games", "Finance", "Lab", "Account", "Chat", "Flows", "Status")))
confere("Swift: janela trata arquivos, downloads e avisos do site", all(t in swift for t in ("runOpenPanelWith", "WKDownloadDelegate", "runJavaScriptAlertPanelWithMessage", "runJavaScriptConfirmPanelWithMessage")))
confere("Swift: barra de menus com StudioLibre, Arquivo, Edição, Visualizar, Abrir e Janela (sem menu Sistema: os itens dele ficam em Arquivo)", all(f'submenuDe(principal, "{m}")' in swift for m in ("StudioLibre", "Arquivo", "Edição", "Visualizar", "Abrir", "Janela")) and 'submenuDe(principal, "Sistema")' not in swift and 'itemDe(arquivo, "Ligar os serviços"' in swift and 'itemDe(arquivo, "Atualizar o StudioLibre e reiniciar"' in swift)
confere("Swift: tela cheia, zoom e atalhos de copiar, colar, recarregar e fechar", all(t in swift for t in ("toggleFullScreen", "fullScreenPrimary", "pageZoom", '"c"', '"v"', '"r"', '"w"')))
confere("Swift: ativa o app de novo logo depois de virar app normal (senão a barra de menus continua a do app anterior)", "func ativarApp()" in swift and "asyncAfter" in swift and swift.count("ativarApp()") >= 3)
confere("Swift: Imprimir usa printOperation do WebKit (NSView não tem print)", "printOperation(with: NSPrintInfo.shared)" in swift and "NSView.print" not in swift)
confere("Swift: reativa pelo sistema se o app não ficar ativo e tem diagnóstico das janelas nos dois menus", "reativarPeloSistema" in swift and "openApplication(at:" in swift and swift.count("Diagnóstico das janelas") >= 3 and "func diagnostico" in swift)
confere("app em português: Info.plist com pt-BR e o script cria pt-BR.lproj (itens do sistema nos menus saem em português)", pl.get("CFBundleDevelopmentRegion") == "pt-BR" and "pt-BR" in pl.get("CFBundleLocalizations", []) and "pt-BR.lproj" in open("scripts/construir_app_mac.sh", encoding="utf-8").read())
confere("Swift: atalhos dos sites em ordem alfabética: Account Command+0; Chat 1, Controls 2, Finance 3, Games 4, Health 5, Lab 6, Learn 7, News 8, Notes 9; Status e Flows sem atalho; menus ordenados", "func teclaDoSite" in swift and 'if nome == "Account" { return "0" }' in swift and '.filter { $0 != "Account" && $0 != "Flows" }.sorted()' in swift and "teclaDoSite(par.0)" in swift and "localizedStandardCompare" in swift)
confere("Swift: Learn no menu Abrir e comando para cadastrar as pastas de estudo (studio learn --sync) nos dois menus", '("learn", "Learn")' in swift and 'func sincronizarLearn' in swift and '["learn", "--sync"]' in swift and swift.count("sincronizarLearn") >= 3)
confere("Swift: o zoom normal saiu de Command+0 (que abre o Account) e foi para Option+Command+0", '"Tamanho normal", #selector(zoomNormal), "0")' in swift and "[.command, .option]" in swift)
confere("Swift: menu StudioLibre com Sobre, Configurações (Command+vírgula), Ocultar e Sair", all(t in swift for t in ('"Sobre o StudioLibre"', '"Configurações…", #selector(abrirConfiguracoes), ","', '"Ocultar o StudioLibre"', '"Mostrar tudo"', '"Sair do StudioLibre"')))
confere("Swift: Configurações com serviço inicial, iniciar com o Mac (LaunchAgent) e ligar serviços ao abrir; também no menu de estado", all(t in swift for t in ("mudouServicoInicial", "mudouEntrada", "mudouLigar", "agenteDeEntrada", '"servicoInicial"', '"ligarAoAbrir"', "setAccessibilityLabel(\"Serviço que abre ao iniciar o app\")")) and swift.count("abrirConfiguracoes") >= 3)
confere("Swift: o LaunchAgent das Configurações é o mesmo do studio app --entrar (mesmo rótulo e caminho)", "io.studiolibre.menu" in swift and "io.studiolibre.menu" in open("scripts/construir_app_mac.sh", encoding="utf-8").read() and "RunAtLoad" in swift)
confere("Info.plist: só https (sem exceção de rede local nem carregamento aberto)", "NSAppTransportSecurity" not in pl)
confere("Swift: todos os sites abrem pelos endereços públicos (Cloudflare Access), não por localhost", '["urls", "--public"]' in swift and "localhost" not in swift)
confere("Swift: abre o Chat sozinho uma vez, fechar a janela não encerra o app e o Dock reabre o Chat", "abrirJanelaInicial" in swift and "applicationShouldTerminateAfterLastWindowClosed" in swift and "return false" in swift and "applicationShouldHandleReopen" in swift)
confere("Swift: itens habilitados pelo estado (Ligar só com tudo desligado; Reiniciar e Parar só com tudo ligado)", "validateMenuItem" in swift and "return !ocupado && !todosLigados()" in swift and "return !ocupado && algumLigado()" in swift)
confere("Swift: o estado olha a porta de cada serviço (lista de studio urls) e mostra quem está fora do ar", 'rodarHeimdall(["urls"])' in swift and "func situacao()" in swift and "Fora do ar" in swift and "de \\(abertos.count + fechados.count) ligados" in swift)
confere("Swift: linhas de estado e grupos Abrir serviço, Nuvem e Celulares no menu de estado", all(t in swift for t in ("menuNeedsUpdate", 'grupo(menu, "Abrir serviço")', 'grupo(menu, "Nuvem (Cloudflare)")', 'grupo(menu, "Celulares")')))
confere("Swift: o app só lê interruptores e a porta do .env, nunca chaves", all(c in swift for c in ("STUDIO_NUVEM", "STUDIO_CAIXA", "STUDIO_CONTROLS_PORT")) and "TOKEN" not in swift)
confere("Swift: rótulo de acessibilidade na barra de menus", "setAccessibilityLabel" in swift)
confere("Swift: não tem segredo, token nem chave", not re.search(r"(hc_|sk-|Bearer|API_TOKEN|password|senha)", swift, re.I))
confere("Swift: chama só o comando heimdall (nada de rm, sudo ou curl)", not re.search(r'"(rm|sudo|curl|sh)"', swift) and "sudo" not in swift)
confere("Swift: cada comando usa subcomandos que existem", all(c in (AQUI / "heimdall.zsh").read_text(encoding="utf-8") for c in ("status)", "restart)", "mailbox)", "usage)", "update)", "urls)", "env)")))
confere("script: sintaxe de shell válida", subprocess.run(["bash", "-n", str(AQUI / "scripts/construir_app_mac.sh")]).returncode == 0)
confere("script: fixa o alvo em macOS 12 (evita o erro -10825)", "-target" in sh and "apple-macos12.0" in sh)
confere("script: assinatura local (ad hoc), sem conta paga", "codesign --force --deep --sign -" in sh)
confere("script: só roda no Mac e avisa se falta o compilador", 'uname' in sh and "xcode-select --install" in sh)
confere("script: mexe só em ~/Applications e no próprio LaunchAgent", "rm -f \"$AGENTE\"" in sh and sh.count("rm -rf") == 1 and 'rm -rf "$ANTIGO_APP"' in sh and "sudo" not in sh)

print("\nFALHAS: %d" % falhas if falhas else "\nTudo certo.")
sys.exit(1 if falhas else 0)
