// Heimdall para o Mac: app de barra de menus. Roda em segundo plano, sem ícone no Dock, e chama o comando `heimdall` por baixo.
// Menus nativos (VoiceOver lê tudo), resultados em janelas de aviso comuns, e os sites do Heimdall abrem em janelas próprias do app (WebKit, o motor do Safari; sem navegador e sem Electron). Não guarda segredo nenhum: quem tem as chaves é o .env.
// Compilado no seu Mac por construir_app_mac.sh (heimdall app).
import AppKit
import Foundation
import WebKit

let pastaHeimdall: String = ProcessInfo.processInfo.environment["HEIMDALL_DIR"] ?? (NSHomeDirectory() + "/heimdall-ai")

func tirarCodigos(_ texto: String) -> String {
    return texto.replacingOccurrences(of: "\u{1B}\\[[0-9;?]*[A-Za-z]", with: "", options: .regularExpression)
}

/// Roda `heimdall <args>` num zsh, com o PATH dos programas do Homebrew, e devolve o texto e o código de saída.
func rodarHeimdall(_ args: [String]) -> (String, Int32) {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/bin/zsh")
    let roteiro = "export HEIMDALL_DIR=\"$1\"; shift; source \"$HEIMDALL_DIR/heimdall.zsh\" 2>/dev/null; heimdall \"$@\""
    p.arguments = ["-c", roteiro, "heimdall", pastaHeimdall] + args
    var ambiente = ProcessInfo.processInfo.environment
    ambiente["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + (ambiente["PATH"] ?? "")
    ambiente["TERM"] = "dumb"
    p.environment = ambiente
    p.standardInput = FileHandle.nullDevice
    let cano = Pipe()
    p.standardOutput = cano
    p.standardError = cano
    do {
        try p.run()
    } catch {
        return ("Não consegui executar o comando: \(error.localizedDescription)", 1)
    }
    let dados = cano.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    let texto = tirarCodigos(String(decoding: dados, as: UTF8.self)).trimmingCharacters(in: .whitespacesAndNewlines)
    return (texto, p.terminationStatus)
}

func avisar(_ titulo: String, _ texto: String) {
    let a = NSAlert()
    a.messageText = titulo
    var corpo = texto.isEmpty ? "(sem texto)" : texto
    if corpo.count > 3000 { corpo = "…" + String(corpo.suffix(3000)) }
    a.informativeText = corpo
    a.addButton(withTitle: "OK")
    NSApp.activate(ignoringOtherApps: true)
    a.runModal()
}

let nomesDosSites: [(String, String)] = [
    ("controls", "Controls"), ("notes", "Notes"), ("news", "News"), ("health", "Health"),
    ("games", "Games"), ("finance", "Finance"), ("cloud", "Cloud"), ("account", "Account"), ("chat", "Chat"),
    ("flows", "Flows"), ("status", "Status"),
]

/// Uma janela do app com um site do Heimdall dentro (WKWebView). Login, cookies e envio de arquivos funcionam como no navegador.
final class JanelaSite: NSObject, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate, NSWindowDelegate {
    let janela: NSWindow
    let web: WKWebView
    var aoFechar: (() -> Void)?
    var destinoDownload: URL?

    init(titulo: String, url: URL) {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = WKWebsiteDataStore.default()
        web = WKWebView(frame: .zero, configuration: config)
        janela = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1100, height: 780),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        super.init()
        janela.title = "Heimdall " + titulo
        janela.contentView = web
        janela.isReleasedWhenClosed = false
        janela.collectionBehavior = [.fullScreenPrimary]
        janela.delegate = self
        janela.center()
        web.navigationDelegate = self
        web.uiDelegate = self
        web.setAccessibilityLabel("Heimdall " + titulo)
        web.load(URLRequest(url: url))
    }

    func mostrar() {
        NSApp.activate(ignoringOtherApps: true)
        janela.makeKeyAndOrderFront(nil)
    }

    func windowWillClose(_ notification: Notification) { aoFechar?() }

    func falhou() {
        let html = "<html lang=\"pt-BR\"><head><meta charset=\"utf-8\"><title>Sem resposta</title></head><body><h1>Sem resposta</h1><p>Não consegui abrir esta página. Confira se os serviços estão ligados: no menu Heimdall, escolha Ligar os serviços, e depois use Command+R para tentar de novo.</p></body></html>"
        web.loadHTMLString(html, baseURL: nil)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { falhou() }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        decisionHandler(navigationAction.shouldPerformDownload ? .download : .allow)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        decisionHandler(navigationResponse.canShowMIMEType ? .allow : .download)
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let pasta = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask)[0]
        var destino = pasta.appendingPathComponent(suggestedFilename)
        var n = 1
        while FileManager.default.fileExists(atPath: destino.path) {
            destino = pasta.appendingPathComponent("\(n)-" + suggestedFilename)
            n += 1
        }
        destinoDownload = destino
        completionHandler(destino)
    }

    func downloadDidFinish(_ download: WKDownload) {
        avisar("Download concluído", "Arquivo salvo em " + (destinoDownload?.path ?? "Downloads") + ".")
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        avisar("Download falhou", error.localizedDescription)
    }

    /// Links que pedem uma janela nova abrem na mesma janela.
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let u = navigationAction.request.url { webView.load(URLRequest(url: u)) }
        return nil
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let painel = NSOpenPanel()
        painel.allowsMultipleSelection = parameters.allowsMultipleSelection
        painel.canChooseDirectories = false
        painel.beginSheetModal(for: janela) { resposta in
            completionHandler(resposta == .OK ? painel.urls : nil)
        }
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let a = NSAlert()
        a.messageText = message
        a.addButton(withTitle: "OK")
        a.beginSheetModal(for: janela) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = NSAlert()
        a.messageText = message
        a.addButton(withTitle: "OK")
        a.addButton(withTitle: "Cancelar")
        a.beginSheetModal(for: janela) { resposta in completionHandler(resposta == .alertFirstButtonReturn) }
    }
}

final class Delegado: NSObject, NSApplicationDelegate {
    var item: NSStatusItem!
    var ocupado = false
    var sites: [(String, String)] = []
    var ultimaBusca = "Ainda não houve busca na caixa de correio desde que o app abriu."
    var temporizador: Timer?
    var janelas: [String: JanelaSite] = [:]

    func applicationDidFinishLaunching(_ n: Notification) {
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "Heimdall"
        item.button?.setAccessibilityLabel("Heimdall, menu de estado")
        montarMenuPrincipal()
        montarMenu()
        carregarSites()
        temporizador = Timer.scheduledTimer(withTimeInterval: 600, repeats: true) { [weak self] _ in
            self?.buscarCaixa(silencioso: true)
        }
    }

    func adicionar(_ menu: NSMenu, _ titulo: String, _ acao: Selector, _ tecla: String = "") {
        let i = NSMenuItem(title: titulo, action: acao, keyEquivalent: tecla)
        i.target = self
        menu.addItem(i)
    }

    func montarMenu() {
        let menu = NSMenu()
        adicionar(menu, "Estado dos serviços", #selector(estado), "e")
        adicionar(menu, "Ligar os serviços", #selector(ligar))
        adicionar(menu, "Reiniciar os serviços", #selector(reiniciar))
        adicionar(menu, "Parar os serviços", #selector(parar))
        menu.addItem(NSMenuItem.separator())

        let abrir = NSMenuItem(title: "Abrir numa janela do app", action: nil, keyEquivalent: "")
        let sub = NSMenu()
        if sites.isEmpty {
            adicionar(sub, "Atualizar a lista de endereços", #selector(recarregarSites))
        } else {
            for (nome, url) in sites {
                let i = NSMenuItem(title: nome, action: #selector(abrirSite(_:)), keyEquivalent: "")
                i.target = self
                i.representedObject = url
                sub.addItem(i)
            }
        }
        abrir.submenu = sub
        menu.addItem(abrir)
        menu.addItem(NSMenuItem.separator())

        adicionar(menu, "Consumo da nuvem (último dia)", #selector(consumo), "u")
        adicionar(menu, "Buscar agora na caixa de correio", #selector(buscarAgora), "b")
        adicionar(menu, "Resultado da última busca na caixa", #selector(mostrarUltimaBusca))
        menu.addItem(NSMenuItem.separator())

        adicionar(menu, "Ligar o modelo grande na nuvem", #selector(nuvemLigar))
        adicionar(menu, "Voltar ao modelo local", #selector(nuvemDesligar))
        adicionar(menu, "Ligar a caixa de correio", #selector(caixaLigar))
        adicionar(menu, "Desligar a caixa de correio", #selector(caixaDesligar))
        menu.addItem(NSMenuItem.separator())

        adicionar(menu, "Atualizar o Heimdall e reiniciar", #selector(atualizar), "a")
        menu.addItem(NSMenuItem.separator())
        adicionar(menu, "Sair do Heimdall", #selector(sair), "q")
        item.menu = menu
    }

    func carregarSites() {
        DispatchQueue.global().async {
            let (texto, codigo) = rodarHeimdall(["urls", "--public"])
            var achados: [(String, String)] = []
            if codigo == 0 {
                for linha in texto.split(separator: "\n") {
                    guard let corte = linha.range(of: ": ") else { continue }
                    let chave = String(linha[linha.startIndex..<corte.lowerBound])
                    let url = String(linha[corte.upperBound...]).trimmingCharacters(in: .whitespaces)
                    if let par = nomesDosSites.first(where: { $0.0 == chave }), url.hasPrefix("http") {
                        achados.append((par.1, url))
                    }
                }
            }
            DispatchQueue.main.async {
                self.sites = achados
                self.montarMenu()
                self.montarMenuPrincipal()
            }
        }
    }

    /// Roda um comando em segundo plano e mostra o resultado numa janela de aviso. Um de cada vez.
    func executar(_ titulo: String, _ args: [String]) {
        if ocupado {
            avisar("Heimdall", "Ainda estou terminando outra tarefa. Tente de novo em instantes.")
            return
        }
        ocupado = true
        item.button?.title = "Heimdall (trabalhando)"
        DispatchQueue.global().async {
            let (texto, codigo) = rodarHeimdall(args)
            DispatchQueue.main.async {
                self.ocupado = false
                self.item.button?.title = "Heimdall"
                avisar(codigo == 0 ? "\(titulo): concluído" : "\(titulo): falhou (código \(codigo))", texto)
            }
        }
    }

    func buscarCaixa(silencioso: Bool) {
        if ocupado { return }
        ocupado = true
        DispatchQueue.global().async {
            let (texto, codigo) = rodarHeimdall(["mailbox", "pull"])
            DispatchQueue.main.async {
                self.ocupado = false
                self.ultimaBusca = texto + (codigo == 0 ? "" : "\n(código de saída \(codigo))")
                self.item.button?.title = codigo == 0 ? "Heimdall" : "Heimdall (atenção)"
                if !silencioso { avisar(codigo == 0 ? "Caixa de correio" : "Caixa de correio: atenção", self.ultimaBusca) }
            }
        }
    }

    @objc func estado() { executar("Estado dos serviços", ["status"]) }
    @objc func ligar() { executar("Ligar os serviços", ["up"]) }
    @objc func reiniciar() { executar("Reiniciar os serviços", ["restart"]) }
    @objc func parar() { executar("Parar os serviços", ["stop"]) }
    @objc func consumo() { executar("Consumo da nuvem", ["usage", "--days", "1"]) }
    @objc func buscarAgora() { buscarCaixa(silencioso: false) }
    @objc func mostrarUltimaBusca() { avisar("Última busca na caixa", ultimaBusca) }
    @objc func nuvemLigar() { executar("Modelo grande na nuvem", ["env", "--set", "HEIMDALL_NUVEM", "1"]) }
    @objc func nuvemDesligar() { executar("Modelo local", ["env", "--set", "HEIMDALL_NUVEM", "0"]) }
    @objc func caixaLigar() { executar("Caixa de correio", ["env", "--set", "HEIMDALL_CAIXA", "1"]) }
    @objc func caixaDesligar() { executar("Caixa de correio", ["env", "--set", "HEIMDALL_CAIXA", "0"]) }
    @objc func atualizar() { executar("Atualizar o Heimdall", ["update", "--restart"]) }
    @objc func recarregarSites() { carregarSites() }

    @objc func abrirSite(_ remetente: NSMenuItem) {
        guard let texto = remetente.representedObject as? String, let url = URL(string: texto) else { return }
        let nome = remetente.title
        if let existente = janelas[nome] {
            existente.mostrar()
            return
        }
        let nova = JanelaSite(titulo: nome, url: url)
        nova.aoFechar = { [weak self] in
            self?.janelas[nome] = nil
            // Sem janelas abertas, o app volta a ficar só na barra de menus.
            if self?.janelas.isEmpty == true { NSApp.setActivationPolicy(.accessory) }
        }
        janelas[nome] = nova
        // Com uma janela aberta o app aparece no Dock e em Command+Tab, para ela não se perder atrás das outras.
        NSApp.setActivationPolicy(.regular)
        nova.mostrar()
    }

    func janelaAtual() -> JanelaSite? {
        return janelas.values.first(where: { $0.janela == NSApp.keyWindow })
    }

    @objc func recarregarJanela() { janelaAtual()?.web.reload() }
    @objc func voltarJanela() { janelaAtual()?.web.goBack() }
    @objc func avancarJanela() { janelaAtual()?.web.goForward() }

    func itemDe(_ menu: NSMenu, _ titulo: String, _ acao: Selector?, _ tecla: String = "", alvo: Bool = true) -> NSMenuItem {
        let i = menu.addItem(withTitle: titulo, action: acao, keyEquivalent: tecla)
        if alvo { i.target = self }
        return i
    }

    func submenuDe(_ principal: NSMenu, _ titulo: String) -> NSMenu {
        let item = NSMenuItem()
        principal.addItem(item)
        let menu = NSMenu(title: titulo)
        item.submenu = menu
        return menu
    }

    @objc func aumentarZoom() { if let w = janelaAtual()?.web { w.pageZoom += 0.1 } }
    @objc func diminuirZoom() { if let w = janelaAtual()?.web { w.pageZoom = max(0.3, w.pageZoom - 0.1) } }
    @objc func zoomNormal() { janelaAtual()?.web.pageZoom = 1.0 }

    /// Barra de menus do app quando uma janela está em primeiro plano: Heimdall, Edição, Visualizar, Sites, Serviços e Janela.
    func montarMenuPrincipal() {
        let principal = NSMenu()

        let menuApp = submenuDe(principal, "Heimdall")
        _ = itemDe(menuApp, "Sair do Heimdall", #selector(sair), "q")

        let edicao = submenuDe(principal, "Edição")
        _ = itemDe(edicao, "Recortar", #selector(NSText.cut(_:)), "x", alvo: false)
        _ = itemDe(edicao, "Copiar", #selector(NSText.copy(_:)), "c", alvo: false)
        _ = itemDe(edicao, "Colar", #selector(NSText.paste(_:)), "v", alvo: false)
        _ = itemDe(edicao, "Selecionar tudo", #selector(NSText.selectAll(_:)), "a", alvo: false)

        let visualizar = submenuDe(principal, "Visualizar")
        let tela = itemDe(visualizar, "Entrar ou sair da tela cheia", #selector(NSWindow.toggleFullScreen(_:)), "f", alvo: false)
        tela.keyEquivalentModifierMask = [.command, .control]
        visualizar.addItem(NSMenuItem.separator())
        _ = itemDe(visualizar, "Recarregar", #selector(recarregarJanela), "r")
        _ = itemDe(visualizar, "Voltar", #selector(voltarJanela), "[")
        _ = itemDe(visualizar, "Avançar", #selector(avancarJanela), "]")
        visualizar.addItem(NSMenuItem.separator())
        _ = itemDe(visualizar, "Aumentar o zoom", #selector(aumentarZoom), "+")
        _ = itemDe(visualizar, "Diminuir o zoom", #selector(diminuirZoom), "-")
        _ = itemDe(visualizar, "Tamanho normal", #selector(zoomNormal), "0")

        let menuSites = submenuDe(principal, "Sites")
        if sites.isEmpty {
            _ = itemDe(menuSites, "Atualizar a lista de endereços", #selector(recarregarSites))
        } else {
            for (n, par) in sites.enumerated() {
                let i = itemDe(menuSites, par.0, #selector(abrirSite(_:)), n < 9 ? String(n + 1) : "")
                i.representedObject = par.1
            }
        }

        let servicos = submenuDe(principal, "Serviços")
        _ = itemDe(servicos, "Estado dos serviços", #selector(estado), "e")
        _ = itemDe(servicos, "Ligar os serviços", #selector(ligar))
        _ = itemDe(servicos, "Reiniciar os serviços", #selector(reiniciar))
        _ = itemDe(servicos, "Parar os serviços", #selector(parar))
        servicos.addItem(NSMenuItem.separator())
        _ = itemDe(servicos, "Consumo da nuvem (último dia)", #selector(consumo), "u")
        _ = itemDe(servicos, "Buscar agora na caixa de correio", #selector(buscarAgora), "b")
        _ = itemDe(servicos, "Atualizar o Heimdall e reiniciar", #selector(atualizar))

        let janela = submenuDe(principal, "Janela")
        _ = itemDe(janela, "Minimizar", #selector(NSWindow.performMiniaturize(_:)), "m", alvo: false)
        _ = itemDe(janela, "Zoom da janela", #selector(NSWindow.performZoom(_:)), "", alvo: false)
        _ = itemDe(janela, "Fechar a janela", #selector(NSWindow.performClose(_:)), "w", alvo: false)

        NSApp.mainMenu = principal
    }

    @objc func sair() { NSApp.terminate(nil) }
}

let aplicativo = NSApplication.shared
let delegado = Delegado()
aplicativo.delegate = delegado
aplicativo.setActivationPolicy(.accessory)
aplicativo.run()
