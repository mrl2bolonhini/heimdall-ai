// Heimdall para o Mac: app de barra de menus. Roda em segundo plano, sem ícone no Dock, e chama o comando `heimdall` por baixo.
// Menus nativos (VoiceOver lê tudo), resultados em janelas de aviso comuns. Não guarda segredo nenhum: quem tem as chaves é o .env.
// Compilado no seu Mac por construir_app_mac.sh (heimdall app).
import AppKit
import Foundation

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
    ("controls", "Controls"), ("notes", "Notas"), ("news", "News"), ("health", "Saúde"),
    ("games", "Jogos"), ("finance", "Finance"), ("cloud", "Cloud"), ("account", "Conta"), ("chat", "Chat (Open WebUI)"),
]

final class Delegado: NSObject, NSApplicationDelegate {
    var item: NSStatusItem!
    var ocupado = false
    var sites: [(String, String)] = []
    var ultimaBusca = "Ainda não houve busca na caixa de correio desde que o app abriu."
    var temporizador: Timer?

    func applicationDidFinishLaunching(_ n: Notification) {
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "Heimdall"
        item.button?.setAccessibilityLabel("Heimdall, menu de estado")
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

        let abrir = NSMenuItem(title: "Abrir", action: nil, keyEquivalent: "")
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
            let (texto, codigo) = rodarHeimdall(["urls"])
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
        if let texto = remetente.representedObject as? String, let url = URL(string: texto) {
            NSWorkspace.shared.open(url)
        }
    }

    @objc func sair() { NSApp.terminate(nil) }
}

let aplicativo = NSApplication.shared
let delegado = Delegado()
aplicativo.delegate = delegado
aplicativo.setActivationPolicy(.accessory)
aplicativo.run()
