#!/usr/bin/env python3
"""Confere o app de barra de menus do Mac sem compilar (aqui não há Swift): arquivos, plist, chaves balanceadas, regras de segurança e do projeto.

    python3 teste_app_mac.py
A compilação de verdade acontece no Mac: heimdall app.
"""
import plistlib
import re
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


swift = (AQUI / "app_mac" / "Heimdall.swift").read_text(encoding="utf-8")
sh = (AQUI / "construir_app_mac.sh").read_text(encoding="utf-8")
pl = plistlib.loads((AQUI / "app_mac" / "Info.plist").read_bytes())

confere("Info.plist: app de barra de menus (sem Dock) e executável certo", pl.get("LSUIElement") is True and pl.get("CFBundleExecutable") == "Heimdall" and pl.get("CFBundlePackageType") == "APPL")
sem_texto = re.sub(r"//[^\n]*", "", re.sub(r'"(?:[^"\\]|\\.)*"', '""', swift))
confere("Swift: chaves e parênteses balanceados", sem_texto.count("{") == sem_texto.count("}") and sem_texto.count("(") == sem_texto.count(")"))
confere("Swift: toda ação do menu tem método @objc", all(f"func {n}(" in swift for n in set(re.findall(r"#selector\((\w+)[(\)]", swift))))
confere("Swift: começa sem ícone no Dock, em segundo plano", ".accessory" in swift and "statusItem" in swift)
confere("Swift: sites em janela própria (WKWebView), sem abrir o navegador", "WKWebView" in swift and "NSWorkspace.shared.open" not in swift)
confere("Swift: nomes dos sites são os nomes reais em inglês", all(f'"{n}"' in swift for n in ("Controls", "Notes", "News", "Health", "Games", "Finance", "Cloud", "Account", "Chat", "Flows", "Status")))
confere("Swift: janela trata arquivos, downloads e avisos do site", all(t in swift for t in ("runOpenPanelWith", "WKDownloadDelegate", "runJavaScriptAlertPanelWithMessage", "runJavaScriptConfirmPanelWithMessage")))
confere("Swift: barra de menus com Heimdall, Edição, Visualizar, Sites, Serviços e Janela", all(f'submenuDe(principal, "{m}")' in swift for m in ("Heimdall", "Edição", "Visualizar", "Abrir", "Sistema", "Janela")))
confere("Swift: tela cheia, zoom e atalhos de copiar, colar, recarregar e fechar", all(t in swift for t in ("toggleFullScreen", "fullScreenPrimary", "pageZoom", '"c"', '"v"', '"r"', '"w"')))
confere("Swift: sites no menu com Command+1 a 9", "n < 9" in swift)
confere("Info.plist: só https (sem exceção de rede local nem carregamento aberto)", "NSAppTransportSecurity" not in pl)
confere("Swift: todos os sites abrem pelos endereços públicos (Cloudflare Access), não por localhost", '["urls", "--public"]' in swift and "localhost" not in swift)
confere("Swift: com janela aberta o app aparece no Dock e em Command+Tab; sem janelas volta à barra de menus", "setActivationPolicy(.regular)" in swift and swift.count("setActivationPolicy(.accessory)") >= 2)
confere("Swift: itens habilitados pelo estado (Ligar só com tudo desligado; Reiniciar e Parar só com tudo ligado)", "validateMenuItem" in swift and "return !ocupado && !servicosLigados()" in swift and "return !ocupado && servicosLigados()" in swift)
confere("Swift: linhas de estado e grupos Abrir serviço, Nuvem e Celulares no menu de estado", all(t in swift for t in ("menuNeedsUpdate", 'grupo(menu, "Abrir serviço")', 'grupo(menu, "Nuvem (Cloudflare)")', 'grupo(menu, "Celulares")')))
confere("Swift: o app só lê interruptores e a porta do .env, nunca chaves", all(c in swift for c in ("HEIMDALL_NUVEM", "HEIMDALL_CAIXA", "HEIMDALL_CONTROLS_PORT")) and "TOKEN" not in swift)
confere("Swift: rótulo de acessibilidade na barra de menus", "setAccessibilityLabel" in swift)
confere("Swift: não tem segredo, token nem chave", not re.search(r"(hc_|sk-|Bearer|API_TOKEN|password|senha)", swift, re.I))
confere("Swift: chama só o comando heimdall (nada de rm, sudo ou curl)", not re.search(r'"(rm|sudo|curl|sh)"', swift) and "sudo" not in swift)
confere("Swift: cada comando usa subcomandos que existem", all(c in (AQUI / "heimdall.zsh").read_text(encoding="utf-8") for c in ("status)", "restart)", "mailbox)", "usage)", "update)", "urls)", "env)")))
confere("script: sintaxe de shell válida", subprocess.run(["bash", "-n", str(AQUI / "construir_app_mac.sh")]).returncode == 0)
confere("script: fixa o alvo em macOS 12 (evita o erro -10825)", "-target" in sh and "apple-macos12.0" in sh)
confere("script: assinatura local (ad hoc), sem conta paga", "codesign --force --deep --sign -" in sh)
confere("script: só roda no Mac e avisa se falta o compilador", 'uname' in sh and "xcode-select --install" in sh)
confere("script: mexe só em ~/Applications e no próprio LaunchAgent", "rm -f \"$AGENTE\"" in sh and "rm -rf" not in sh and "sudo" not in sh)

print("\nFALHAS: %d" % falhas if falhas else "\nTudo certo.")
sys.exit(1 if falhas else 0)
