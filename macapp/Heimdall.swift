// Heimdall para o Mac: app de barra de menus. Roda em segundo plano, sem ícone no Dock, e chama o comando `heimdall` por baixo.
// Menus nativos (VoiceOver lê tudo), resultados em janelas de aviso comuns, e os sites do Heimdall abrem em janelas próprias do app (WebKit, o motor do Safari; sem navegador e sem Electron). Não guarda segredo nenhum: quem tem as chaves é o .env.
// Compilado no seu Mac por scripts/construir_app_mac.sh (heimdall app).
import AppKit
import Foundation
import UserNotifications
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

/// Lê um valor do .env do projeto. O app só usa isto para ver interruptores (0 ou 1) e a porta do Controls; nunca lê chaves.
func valorDoEnv(_ chave: String) -> String? {
    guard let texto = try? String(contentsOfFile: pastaHeimdall + "/.env", encoding: .utf8) else { return nil }
    for linha in texto.split(separator: "\n") {
        let l = linha.trimmingCharacters(in: .whitespaces)
        let sem = l.hasPrefix("export ") ? String(l.dropFirst(7)) : l
        if sem.hasPrefix(chave + "=") {
            let v = String(sem.dropFirst(chave.count + 1)).trimmingCharacters(in: CharacterSet(charactersIn: "\"' "))
            return v.isEmpty ? nil : v
        }
    }
    return nil
}

/// Diz se há algo escutando nesta porta do próprio Mac (é assim que o app sabe se os serviços estão ligados).
func portaAberta(_ porta: Int) -> Bool {
    let fd = socket(AF_INET, SOCK_STREAM, 0)
    if fd < 0 { return false }
    defer { close(fd) }
    var endereco = sockaddr_in()
    endereco.sin_family = sa_family_t(AF_INET)
    endereco.sin_port = in_port_t(porta).bigEndian
    endereco.sin_addr.s_addr = inet_addr("127.0.0.1")
    let r = withUnsafePointer(to: &endereco) {
        $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
        }
    }
    return r == 0
}

/// Torna o Heimdall o app ativo (é o app ativo que manda na barra de menus do alto). Do macOS 14 em diante o método antigo foi substituído.
func ativarApp() {
    if #available(macOS 14.0, *) { NSApp.activate() } else { NSApp.activate(ignoringOtherApps: true) }
}

/// Pede ao próprio sistema (LaunchServices) que ative o Heimdall, como se ele tivesse sido aberto de novo. É o caminho que o macOS sempre aceita.
func reativarPeloSistema() {
    let c = NSWorkspace.OpenConfiguration()
    c.activates = true
    NSWorkspace.shared.openApplication(at: Bundle.main.bundleURL, configuration: c, completionHandler: nil)
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
    ("controls", "Controls"), ("notes", "Notes"), ("learn", "Learn"), ("news", "News"), ("health", "Health"),
    ("games", "Games"), ("finance", "Finance"), ("cloud", "Cloud"), ("account", "Account"), ("chat", "Chat"),
    ("flows", "Flows"), ("status", "Status"),
]

/// Atalho de teclado de cada site no menu Abrir: Account é Command+0; os demais, em ordem alfabética, de 1 a 9, sem Account e Flows
/// (Chat 1, Cloud 2, Controls 3, Finance 4, Games 5, Health 6, Learn 7, News 8, Notes 9). Status e Flows ficam sem atalho.
func teclaDoSite(_ nome: String) -> String {
    if nome == "Account" { return "0" }
    let ordem = nomesDosSites.map { $0.1 }.filter { $0 != "Account" && $0 != "Flows" }.sorted()
    if let n = ordem.firstIndex(of: nome), n < 9 { return String(n + 1) }
    return ""
}

/// Preferências do app (UserDefaults): serviço que abre ao iniciar ("" = nenhum; padrão Chat) e ligar os serviços ao abrir o app.
func servicoInicial() -> String {
    if UserDefaults.standard.object(forKey: "servicoInicial") == nil { return "Chat" }
    return UserDefaults.standard.string(forKey: "servicoInicial") ?? ""
}

let agenteDeEntrada = NSHomeDirectory() + "/Library/LaunchAgents/tech.heimdall.menu.plist"
func entradaAtiva() -> Bool { return FileManager.default.fileExists(atPath: agenteDeEntrada) }

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
        ativarApp()
        janela.makeKeyAndOrderFront(nil)
        // Logo depois de o app virar .regular o macOS ainda não o considera ativo, e a barra de menus do alto continua a do app anterior.
        // Ativar de novo um instante depois resolve.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { [weak self] in
            ativarApp()
            self?.janela.makeKeyAndOrderFront(nil)
        }
        // Se mesmo assim o macOS não considerar o app ativo, a barra de menus do alto seria a de outro app: pede a ativação ao sistema.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
            if !NSApp.isActive { reativarPeloSistema() }
        }
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

final class Delegado: NSObject, NSApplicationDelegate, NSMenuDelegate, UNUserNotificationCenterDelegate {
    var item: NSStatusItem!
    var ocupado = false
    var sites: [(String, String)] = []
    var ultimaBusca = "Ainda não houve sincronização com os celulares desde que o app abriu."
    var portas: [(String, Int)] = []
    var situacaoCache: (Date, [String], [String])?
    var temporizador: Timer?
    var janelas: [String: JanelaSite] = [:]

    func applicationDidFinishLaunching(_ n: Notification) {
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "Heimdall"
        item.button?.setAccessibilityLabel("Heimdall, menu de estado")
        montarMenuPrincipal()
        montarMenu()
        carregarPortas()
        carregarSites()
        if UserDefaults.standard.bool(forKey: "ligarAoAbrir") {
            // Dá tempo de ler as portas e só liga se nada do Heimdall estiver no ar.
            DispatchQueue.main.asyncAfter(deadline: .now() + 4) { [weak self] in
                guard let self = self else { return }
                if self.situacao().0.isEmpty { self.ligar() }
            }
        }
        temporizador = Timer.scheduledTimer(withTimeInterval: 600, repeats: true) { [weak self] _ in
            self?.buscarCaixa(silencioso: true)
        }
        iniciarAvisos()
    }

    // --- avisos nativos: o Heimdall grava o aviso completo em db/alerts/ (só no Mac) e o app mostra como notificação do macOS
    var temporizadorAvisos: Timer?
    var avisosPermitidos: Bool { UserDefaults.standard.object(forKey: "avisosNoMac") as? Bool ?? true }

    func pastaDeAvisos() -> String {
        // Pastas novas (db/alerts); se o Mac ainda estiver com as antigas (banco/avisos_mac), usa-as até o Heimdall migrar.
        let fm = FileManager.default
        var base = valorDoEnv("HEIMDALL_DB_DIR") ?? (pastaHeimdall + "/db")
        if valorDoEnv("HEIMDALL_DB_DIR") == nil && !fm.fileExists(atPath: base) && fm.fileExists(atPath: pastaHeimdall + "/banco") {
            base = pastaHeimdall + "/banco"
        }
        base = (base as NSString).expandingTildeInPath
        if !fm.fileExists(atPath: base + "/alerts") && fm.fileExists(atPath: base + "/avisos_mac") {
            return base + "/avisos_mac"
        }
        return base + "/alerts"
    }

    func iniciarAvisos() {
        guard valorDoEnv("HEIMDALL_AVISOS_MAC") != "0" else { return }
        let centro = UNUserNotificationCenter.current()
        centro.delegate = self
        centro.requestAuthorization(options: [.alert, .sound, .badge]) { _, _ in }
        temporizadorAvisos = Timer.scheduledTimer(withTimeInterval: 4, repeats: true) { [weak self] _ in self?.lerAvisos() }
    }

    func lerAvisos() {
        let pasta = pastaDeAvisos()
        let fm = FileManager.default
        guard let nomes = try? fm.contentsOfDirectory(atPath: pasta) else { return }
        for nome in nomes.filter({ $0.hasSuffix(".json") }).sorted() {
            let caminho = pasta + "/" + nome
            defer { try? fm.removeItem(atPath: caminho) }   // o arquivo some depois de lido; com o aviso desligado, também (não acumula)
            guard avisosPermitidos,
                  let dados = fm.contents(atPath: caminho),
                  let o = try? JSONSerialization.jsonObject(with: dados) as? [String: Any] else { continue }
            mostrarAviso(titulo: o["titulo"] as? String ?? "Heimdall", corpo: o["corpo"] as? String ?? "",
                         grupo: o["grupo"] as? String ?? "heimdall", nivel: o["nivel"] as? String ?? "active")
        }
    }

    func mostrarAviso(titulo: String, corpo: String, grupo: String, nivel: String) {
        let c = UNMutableNotificationContent()
        c.title = titulo
        c.body = corpo
        c.threadIdentifier = grupo
        c.sound = .default
        if #available(macOS 12.0, *) {
            switch nivel {
            case "critical", "timeSensitive": c.interruptionLevel = .timeSensitive
            case "passive": c.interruptionLevel = .passive; c.sound = nil
            default: c.interruptionLevel = .active
            }
        }
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: UUID().uuidString, content: c, trigger: nil))
    }

    // Com o app em primeiro plano o macOS não mostra a notificação sozinho: pede para mostrar mesmo assim.
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .list, .sound])
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        ativarApp()
        completionHandler()
    }

    @objc func mudouAvisos() { UserDefaults.standard.set(caixaAvisos.state == .on, forKey: "avisosNoMac") }

    func adicionar(_ menu: NSMenu, _ titulo: String, _ acao: Selector, _ tecla: String = "") {
        let i = NSMenuItem(title: titulo, action: acao, keyEquivalent: tecla)
        i.target = self
        menu.addItem(i)
    }

    func grupo(_ menu: NSMenu, _ titulo: String) -> NSMenu {
        let i = NSMenuItem(title: titulo, action: nil, keyEquivalent: "")
        let sub = NSMenu(title: titulo)
        i.submenu = sub
        menu.addItem(i)
        return sub
    }

    // --- estado: o que está ligado agora (cada serviço tem a sua porta; os itens do menu se habilitam por isto)
    func carregarPortas() {
        DispatchQueue.global().async {
            let (texto, codigo) = rodarHeimdall(["urls"])
            var achadas: [(String, Int)] = []
            if codigo == 0 {
                for linha in texto.split(separator: "\n") {
                    guard let corte = linha.range(of: ": ") else { continue }
                    let nome = String(linha[linha.startIndex..<corte.lowerBound])
                    let url = String(linha[corte.upperBound...]).trimmingCharacters(in: .whitespaces)
                    if let porta = URL(string: url)?.port { achadas.append((nome, porta)) }
                }
            }
            DispatchQueue.main.async {
                self.portas = achadas
                self.situacaoCache = nil
            }
        }
    }

    /// (ligados, desligados): olha a porta de cada serviço. Sem a lista de portas, olha só a do Controls.
    func situacao() -> ([String], [String]) {
        if let c = situacaoCache, Date().timeIntervalSince(c.0) < 2 { return (c.1, c.2) }
        var lista = portas
        if lista.isEmpty { lista = [("controls", Int(valorDoEnv("HEIMDALL_CONTROLS_PORT") ?? "8017") ?? 8017)] }
        var abertos: [String] = []
        var fechados: [String] = []
        for (nome, porta) in lista {
            if portaAberta(porta) { abertos.append(nome) } else { fechados.append(nome) }
        }
        situacaoCache = (Date(), abertos, fechados)
        return (abertos, fechados)
    }
    func todosLigados() -> Bool { return situacao().1.isEmpty }
    func algumLigado() -> Bool { return !situacao().0.isEmpty }

    func resumoServicos() -> String {
        let (abertos, fechados) = situacao()
        if fechados.isEmpty { return "Serviços do Heimdall: todos ligados (\(abertos.count))" }
        if abertos.isEmpty { return "Serviços do Heimdall: desligados" }
        return "Serviços do Heimdall: \(abertos.count) de \(abertos.count + fechados.count) ligados"
    }

    func nuvemLigada() -> Bool { return valorDoEnv("HEIMDALL_NUVEM") == "1" }
    func syncLigada() -> Bool { return valorDoEnv("HEIMDALL_CAIXA") == "1" }

    /// Liga ou desliga cada item conforme o estado: Ligar só vale com os serviços desligados; Reiniciar e Parar, só com eles ligados.
    @objc func validateMenuItem(_ m: NSMenuItem) -> Bool {
        guard let a = m.action else { return false }
        if a == #selector(ligar) { return !ocupado && !todosLigados() }
        if a == #selector(reiniciar) || a == #selector(parar) { return !ocupado && algumLigado() }
        if a == #selector(alternarNuvem) {
            m.title = nuvemLigada() ? "Desligar o modelo na nuvem (volta ao modelo local)" : "Ligar o modelo grande na nuvem"
            return !ocupado
        }
        if a == #selector(alternarSync) {
            m.title = syncLigada() ? "Desligar a sincronização com os celulares" : "Ligar a sincronização com os celulares"
            return !ocupado
        }
        if a == #selector(sincronizarAgora) { return !ocupado && syncLigada() }
        if a == #selector(estado) || a == #selector(consumo) || a == #selector(atualizar) { return !ocupado }
        return true
    }

    /// Linhas de estado no alto do menu de estado (o VoiceOver as lê como itens sem ação).
    func menuNeedsUpdate(_ menu: NSMenu) {
        situacaoCache = nil
        menu.item(withTag: 101)?.title = resumoServicos()
        menu.item(withTag: 102)?.title = nuvemLigada() ? "Modelo de IA: nuvem (gpt-oss-120b)" : "Modelo de IA: local"
        menu.item(withTag: 103)?.title = syncLigada() ? "Celulares: sincronização ligada" : "Celulares: sincronização desligada"
    }

    func montarMenu() {
        let menu = NSMenu()
        menu.delegate = self
        for (tag, texto) in [(101, "Serviços do Heimdall"), (102, "Modelo de IA"), (103, "Celulares")] {
            let linha = NSMenuItem(title: texto, action: nil, keyEquivalent: "")
            linha.tag = tag
            menu.addItem(linha)
        }
        menu.addItem(NSMenuItem.separator())

        let abrir = grupo(menu, "Abrir serviço")
        if sites.isEmpty {
            adicionar(abrir, "Atualizar a lista de endereços", #selector(recarregarSites))
        } else {
            for (nome, url) in sites {
                let i = NSMenuItem(title: nome, action: #selector(abrirSite(_:)), keyEquivalent: "")
                i.target = self
                i.representedObject = url
                abrir.addItem(i)
            }
        }
        menu.addItem(NSMenuItem.separator())

        adicionar(menu, "Ligar os serviços", #selector(ligar))
        adicionar(menu, "Reiniciar os serviços", #selector(reiniciar))
        adicionar(menu, "Parar os serviços", #selector(parar))
        adicionar(menu, "Ver o estado em detalhe", #selector(estado), "e")
        adicionar(menu, "Diagnóstico das janelas", #selector(diagnostico))
        adicionar(menu, "Configurações…", #selector(abrirConfiguracoes), ",")
        menu.addItem(NSMenuItem.separator())

        let nuvem = grupo(menu, "Nuvem (Cloudflare)")
        adicionar(nuvem, "Consumo e custo do último dia", #selector(consumo), "u")
        adicionar(nuvem, "Ligar o modelo grande na nuvem", #selector(alternarNuvem))

        let learn = grupo(menu, "Learn")
        adicionar(learn, "Cadastrar as pastas de estudo novas", #selector(sincronizarLearn))

        let celulares = grupo(menu, "Celulares")
        adicionar(celulares, "Sincronizar agora", #selector(sincronizarAgora), "b")
        adicionar(celulares, "Resultado da última sincronização", #selector(mostrarUltimaBusca))
        adicionar(celulares, "Ligar a sincronização com os celulares", #selector(alternarSync))
        menu.addItem(NSMenuItem.separator())

        adicionar(menu, "Atualizar o Heimdall e reiniciar", #selector(atualizar), "a")
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
                self.sites = achados.sorted { $0.0.localizedStandardCompare($1.0) == .orderedAscending }   // menus em ordem alfabética
                self.montarMenu()
                self.montarMenuPrincipal()
                self.abrirJanelaInicial()
            }
        }
    }

    /// Roda um comando em segundo plano e mostra o resultado numa janela de aviso. Um de cada vez.
    func executar(_ titulo: String, _ args: [String], prefixo: String = "") {
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
                self.situacaoCache = nil
                self.item.button?.title = "Heimdall"
                avisar(codigo == 0 ? "\(titulo): concluído" : "\(titulo): falhou (código \(codigo))", prefixo.isEmpty ? texto : prefixo + "\n\n" + texto)
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
                if !silencioso { avisar(codigo == 0 ? "Sincronização com os celulares" : "Sincronização com os celulares: atenção", self.ultimaBusca) }
            }
        }
    }

    @objc func estado() {
        let (abertos, fechados) = situacao()
        var resumo = "Ligados: " + (abertos.isEmpty ? "nenhum" : abertos.joined(separator: ", ")) + "."
        resumo += "\nFora do ar: " + (fechados.isEmpty ? "nenhum" : fechados.joined(separator: ", ")) + "."
        executar("Estado dos serviços", ["status"], prefixo: resumo)
    }
    @objc func ligar() { executar("Ligar os serviços", ["up"]) }
    @objc func reiniciar() { executar("Reiniciar os serviços", ["restart"]) }
    @objc func parar() { executar("Parar os serviços", ["stop"]) }
    @objc func consumo() { executar("Consumo da nuvem", ["usage", "--days", "1"]) }
    @objc func sincronizarLearn() { executar("Pastas do Learn", ["learn", "--sync"]) }
    @objc func sincronizarAgora() { buscarCaixa(silencioso: false) }
    @objc func mostrarUltimaBusca() { avisar("Última sincronização com os celulares", ultimaBusca) }
    @objc func alternarNuvem() { executar("Modelo de IA", ["env", "--set", "HEIMDALL_NUVEM", nuvemLigada() ? "0" : "1"]) }
    @objc func alternarSync() { executar("Sincronização com os celulares", ["env", "--set", "HEIMDALL_CAIXA", syncLigada() ? "0" : "1"]) }
    @objc func atualizar() { executar("Atualizar o Heimdall", ["update", "--restart"]) }
    @objc func recarregarSites() { carregarSites() }

    @objc func abrirSite(_ remetente: NSMenuItem) {
        guard let texto = remetente.representedObject as? String else { return }
        abrirJanela(remetente.title, texto)
    }

    /// Abre (ou traz para a frente) a janela de um site. O app é sempre um app normal (Dock, Command+Tab e barra de menus do alto): trocar de
    /// "só barra de menus" para "app normal" com a janela já aberta fazia o macOS não tratar o Heimdall como app ativo.
    func abrirJanela(_ nome: String, _ texto: String) {
        guard let url = URL(string: texto) else { return }
        if let existente = janelas[nome] {
            existente.mostrar()
            return
        }
        let nova = JanelaSite(titulo: nome, url: url)
        nova.aoFechar = { [weak self] in self?.janelas[nome] = nil }
        janelas[nome] = nova
        nova.mostrar()
    }

    /// Janela inicial: assim que a lista de endereços chega, abre o serviço escolhido nas Configurações (padrão: Chat) uma única vez.
    var abriuInicial = false
    func abrirJanelaInicial() {
        let nome = servicoInicial()
        guard !abriuInicial, !nome.isEmpty, let par = sites.first(where: { $0.0 == nome }) else { return }
        abriuInicial = true
        abrirJanela(par.0, par.1)
    }

    /// Clique no ícone do Dock sem janelas: abre o Chat de novo. Fechar a janela não encerra o app (ele continua na barra de estado).
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag {
            let nome = servicoInicial()
            if let par = sites.first(where: { $0.0 == nome }) ?? sites.first(where: { $0.0 == "Chat" }) ?? sites.first { abrirJanela(par.0, par.1) }
        }
        return true
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { return false }

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

    // MARK: Configurações

    var janelaConfig: NSWindow?
    let escolhaInicial = NSPopUpButton(frame: .zero, pullsDown: false)
    var caixaEntrar: NSButton!
    var caixaLigar: NSButton!
    var caixaAvisos: NSButton!

    @objc func abrirConfiguracoes() {
        if janelaConfig == nil {
            let rotulo = NSTextField(labelWithString: "Serviço que abre ao iniciar o app:")
            escolhaInicial.removeAllItems()
            escolhaInicial.addItem(withTitle: "Nenhum (só a barra de estado)")
            escolhaInicial.addItems(withTitles: nomesDosSites.map { $0.1 })
            escolhaInicial.target = self
            escolhaInicial.action = #selector(mudouServicoInicial)
            escolhaInicial.setAccessibilityLabel("Serviço que abre ao iniciar o app")
            caixaEntrar = NSButton(checkboxWithTitle: "Iniciar o Heimdall quando eu ligar o Mac", target: self, action: #selector(mudouEntrada))
            caixaLigar = NSButton(checkboxWithTitle: "Ligar os serviços do Heimdall ao abrir o app", target: self, action: #selector(mudouLigar))
            caixaAvisos = NSButton(checkboxWithTitle: "Mostrar os avisos do Heimdall como notificações do Mac", target: self, action: #selector(mudouAvisos))
            let pilha = NSStackView(views: [rotulo, escolhaInicial, caixaEntrar, caixaLigar, caixaAvisos])
            pilha.orientation = .vertical
            pilha.alignment = .leading
            pilha.spacing = 14
            pilha.translatesAutoresizingMaskIntoConstraints = false
            let j = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 500, height: 230), styleMask: [.titled, .closable], backing: .buffered, defer: false)
            j.title = "Configurações do Heimdall"
            j.isReleasedWhenClosed = false
            if let conteudo = j.contentView {
                conteudo.addSubview(pilha)
                NSLayoutConstraint.activate([
                    pilha.leadingAnchor.constraint(equalTo: conteudo.leadingAnchor, constant: 24),
                    pilha.trailingAnchor.constraint(lessThanOrEqualTo: conteudo.trailingAnchor, constant: -24),
                    pilha.topAnchor.constraint(equalTo: conteudo.topAnchor, constant: 24),
                ])
            }
            j.center()
            janelaConfig = j
        }
        // O que está na tela reflete o que está gravado agora (o arquivo de entrada pode ter sido mexido pelo terminal).
        let atual = servicoInicial()
        escolhaInicial.selectItem(withTitle: atual.isEmpty ? "Nenhum (só a barra de estado)" : atual)
        caixaEntrar.state = entradaAtiva() ? .on : .off
        caixaLigar.state = UserDefaults.standard.bool(forKey: "ligarAoAbrir") ? .on : .off
        caixaAvisos.state = avisosPermitidos ? .on : .off
        ativarApp()
        janelaConfig?.makeKeyAndOrderFront(nil)
    }

    @objc func mudouServicoInicial() {
        let t = escolhaInicial.titleOfSelectedItem ?? ""
        UserDefaults.standard.set(t.hasPrefix("Nenhum") ? "" : t, forKey: "servicoInicial")
    }

    @objc func mudouLigar() { UserDefaults.standard.set(caixaLigar.state == .on, forKey: "ligarAoAbrir") }

    /// Iniciar ao ligar o Mac: cria ou apaga o mesmo LaunchAgent que o heimdall app --entrar cria. Vale a partir do próximo login.
    @objc func mudouEntrada() {
        if caixaEntrar.state == .on {
            let executavel = Bundle.main.executablePath ?? (NSHomeDirectory() + "/Applications/Heimdall.app/Contents/MacOS/Heimdall")
            let texto = """
            <?xml version="1.0" encoding="UTF-8"?>
            <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
            <plist version="1.0"><dict>
            <key>Label</key><string>tech.heimdall.menu</string>
            <key>ProgramArguments</key><array><string>\(executavel)</string></array>
            <key>RunAtLoad</key><true/>
            </dict></plist>

            """
            try? FileManager.default.createDirectory(atPath: NSHomeDirectory() + "/Library/LaunchAgents", withIntermediateDirectories: true)
            do { try texto.write(toFile: agenteDeEntrada, atomically: true, encoding: .utf8) } catch {
                caixaEntrar.state = .off
                avisar("Configurações", "Não consegui ativar o início com o Mac: " + error.localizedDescription)
            }
        } else {
            do { try FileManager.default.removeItem(atPath: agenteDeEntrada) } catch {
                caixaEntrar.state = .on
                avisar("Configurações", "Não consegui desativar o início com o Mac: " + error.localizedDescription)
            }
        }
    }

    @objc func diagnostico() {
        let politica = ["normal (regular)", "só barra de menus (accessory)", "proibido (prohibited)"][min(max(NSApp.activationPolicy().rawValue, 0), 2)]
        let primeiro = NSWorkspace.shared.frontmostApplication?.localizedName ?? "nenhum"
        let menus = NSApp.mainMenu?.items.map { $0.submenu?.title ?? $0.title }.joined(separator: ", ") ?? "nenhum"
        avisar("Diagnóstico das janelas", """
        Política do app: \(politica)
        O Heimdall é o app ativo: \(NSApp.isActive ? "sim" : "não")
        App em primeiro plano agora: \(primeiro)
        Menus montados: \(menus)
        Janelas abertas: \(janelas.count); janela em foco: \(NSApp.keyWindow != nil ? "sim" : "não")
        """)
    }

    @objc func imprimirJanela() {
        guard let j = janelaAtual() else { return }
        let operacao = j.web.printOperation(with: NSPrintInfo.shared)
        operacao.view?.frame = j.web.bounds
        operacao.runModal(for: j.janela, delegate: nil, didRun: nil, contextInfo: nil)
    }

    @objc func aumentarZoom() { if let w = janelaAtual()?.web { w.pageZoom += 0.1 } }
    @objc func diminuirZoom() { if let w = janelaAtual()?.web { w.pageZoom = max(0.3, w.pageZoom - 0.1) } }
    @objc func zoomNormal() { janelaAtual()?.web.pageZoom = 1.0 }

    /// Barra de menus do app quando uma janela está em primeiro plano: Heimdall, Arquivo (com os itens do sistema), Edição, Visualizar, Abrir e Janela.
    func montarMenuPrincipal() {
        let principal = NSMenu()

        let menuApp = submenuDe(principal, "Heimdall")
        _ = itemDe(menuApp, "Sobre o Heimdall", #selector(NSApplication.orderFrontStandardAboutPanel(_:)), "", alvo: false)
        menuApp.addItem(NSMenuItem.separator())
        _ = itemDe(menuApp, "Configurações…", #selector(abrirConfiguracoes), ",")
        menuApp.addItem(NSMenuItem.separator())
        _ = itemDe(menuApp, "Ocultar o Heimdall", #selector(NSApplication.hide(_:)), "h", alvo: false)
        let outros = itemDe(menuApp, "Ocultar os outros", #selector(NSApplication.hideOtherApplications(_:)), "h", alvo: false)
        outros.keyEquivalentModifierMask = [.command, .option]
        _ = itemDe(menuApp, "Mostrar tudo", #selector(NSApplication.unhideAllApplications(_:)), "", alvo: false)
        menuApp.addItem(NSMenuItem.separator())
        _ = itemDe(menuApp, "Sair do Heimdall", #selector(sair), "q")

        let arquivo = submenuDe(principal, "Arquivo")
        _ = itemDe(arquivo, "Imprimir…", #selector(imprimirJanela), "p")
        arquivo.addItem(NSMenuItem.separator())
        _ = itemDe(arquivo, "Ligar os serviços", #selector(ligar))
        _ = itemDe(arquivo, "Reiniciar os serviços", #selector(reiniciar))
        _ = itemDe(arquivo, "Parar os serviços", #selector(parar))
        _ = itemDe(arquivo, "Ver o estado em detalhe", #selector(estado), "e")
        _ = itemDe(arquivo, "Diagnóstico das janelas", #selector(diagnostico))
        arquivo.addItem(NSMenuItem.separator())
        _ = itemDe(arquivo, "Consumo e custo da nuvem (último dia)", #selector(consumo), "u")
        _ = itemDe(arquivo, "Ligar o modelo grande na nuvem", #selector(alternarNuvem))
        arquivo.addItem(NSMenuItem.separator())
        _ = itemDe(arquivo, "Cadastrar as pastas de estudo novas do Learn", #selector(sincronizarLearn))
        arquivo.addItem(NSMenuItem.separator())
        _ = itemDe(arquivo, "Sincronizar agora com os celulares", #selector(sincronizarAgora), "b")
        _ = itemDe(arquivo, "Resultado da última sincronização", #selector(mostrarUltimaBusca))
        _ = itemDe(arquivo, "Ligar a sincronização com os celulares", #selector(alternarSync))
        arquivo.addItem(NSMenuItem.separator())
        _ = itemDe(arquivo, "Atualizar o Heimdall e reiniciar", #selector(atualizar))
        arquivo.addItem(NSMenuItem.separator())
        _ = itemDe(arquivo, "Fechar a janela", #selector(NSWindow.performClose(_:)), "w", alvo: false)

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
        let normal = itemDe(visualizar, "Tamanho normal", #selector(zoomNormal), "0")
        normal.keyEquivalentModifierMask = [.command, .option]   // Command+0 abre o Account

        let menuSites = submenuDe(principal, "Abrir")
        if sites.isEmpty {
            _ = itemDe(menuSites, "Atualizar a lista de endereços", #selector(recarregarSites))
        } else {
            for par in sites {
                let i = itemDe(menuSites, par.0, #selector(abrirSite(_:)), teclaDoSite(par.0))
                i.representedObject = par.1
            }
        }

        let janela = submenuDe(principal, "Janela")
        _ = itemDe(janela, "Minimizar", #selector(NSWindow.performMiniaturize(_:)), "m", alvo: false)
        _ = itemDe(janela, "Zoom da janela", #selector(NSWindow.performZoom(_:)), "", alvo: false)

        NSApp.mainMenu = principal
    }

    @objc func sair() { NSApp.terminate(nil) }
}

let aplicativo = NSApplication.shared
let delegado = Delegado()
aplicativo.delegate = delegado
aplicativo.setActivationPolicy(.regular)
aplicativo.run()
