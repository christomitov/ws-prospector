import Cocoa
#if canImport(Sparkle)
import Sparkle
#endif

final class LauncherAppDelegate: NSObject, NSApplicationDelegate {
    private let appURL = URL(string: "http://127.0.0.1:8000")!
    private var serverProcess: Process?
    private var lastDashboardOpenAt = Date.distantPast
    #if canImport(Sparkle)
    private var updaterController: SPUStandardUpdaterController?
    #endif

    func applicationDidFinishLaunching(_ notification: Notification) {
        configureMenu()
        setupUpdater()
        startServer()
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { [weak self] in
            self?.openDashboardNow()
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        openDashboardDebounced()
        return false
    }

    func applicationWillTerminate(_ notification: Notification) {
        stopServer()
    }

    func applicationDockMenu(_ sender: NSApplication) -> NSMenu? {
        return buildActionsMenu(includeKeyEquivalents: false)
    }

    @objc private func openDashboard(_ sender: Any?) {
        openDashboardDebounced()
    }

    private func openDashboardDebounced() {
        let now = Date()
        guard now.timeIntervalSince(lastDashboardOpenAt) > 1.5 else { return }
        openDashboardNow()
    }

    private func openDashboardNow() {
        lastDashboardOpenAt = Date()
        NSWorkspace.shared.open(appURL)
    }

    @objc private func quitApp(_ sender: Any?) {
        NSApp.terminate(nil)
    }

    private func configureMenu() {
        let mainMenu = NSMenu()
        let appMenuItem = NSMenuItem()
        mainMenu.addItem(appMenuItem)

        let appMenu = buildActionsMenu(includeKeyEquivalents: true)
        appMenuItem.submenu = appMenu
        NSApp.mainMenu = mainMenu
    }

    private func buildActionsMenu(includeKeyEquivalents: Bool) -> NSMenu {
        let menu = NSMenu()
        #if canImport(Sparkle)
        menu.addItem(
            withTitle: "Check for Updates...",
            action: #selector(checkForUpdates(_:)),
            keyEquivalent: ""
        )
        menu.addItem(NSMenuItem.separator())
        #endif
        menu.addItem(
            withTitle: "Open Dashboard",
            action: #selector(openDashboard(_:)),
            keyEquivalent: includeKeyEquivalents ? "o" : ""
        )
        menu.addItem(NSMenuItem.separator())
        menu.addItem(
            withTitle: "Quit Wealthsimple Prospector",
            action: #selector(quitApp(_:)),
            keyEquivalent: includeKeyEquivalents ? "q" : ""
        )
        menu.items.forEach { $0.target = self }
        return menu
    }

    private func setupUpdater() {
        #if canImport(Sparkle)
        guard
            let info = Bundle.main.infoDictionary,
            let feedURL = info["SUFeedURL"] as? String,
            !feedURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
            let publicKey = info["SUPublicEDKey"] as? String,
            !publicKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            return
        }
        updaterController = SPUStandardUpdaterController(
            startingUpdater: true,
            updaterDelegate: nil,
            userDriverDelegate: nil
        )
        #endif
    }

    @objc private func checkForUpdates(_ sender: Any?) {
        #if canImport(Sparkle)
        updaterController?.checkForUpdates(sender)
        #endif
    }

    private func startServer() {
        guard serverProcess == nil else { return }
        guard let executableURL = Bundle.main.resourceURL?.appendingPathComponent("app/wealthsimple-prospector") else {
            NSApp.terminate(nil)
            return
        }

        let process = Process()
        process.executableURL = executableURL
        process.arguments = []
        var env = ProcessInfo.processInfo.environment
        env["WSP_OPEN_BROWSER"] = "0"
        process.environment = env
        process.terminationHandler = { _ in
            DispatchQueue.main.async {
                NSApp.terminate(nil)
            }
        }

        do {
            try process.run()
            serverProcess = process
        } catch {
            NSApp.terminate(nil)
        }
    }

    private func stopServer() {
        guard let process = serverProcess else { return }
        if process.isRunning {
            process.terminate()
            process.waitUntilExit()
        }
        serverProcess = nil
    }
}

let app = NSApplication.shared
let delegate = LauncherAppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
