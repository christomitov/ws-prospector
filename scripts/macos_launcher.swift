import Cocoa

final class LauncherAppDelegate: NSObject, NSApplicationDelegate {
    private let appURL = URL(string: "http://127.0.0.1:8000")!
    private var serverProcess: Process?
    private var lastDashboardOpenAt = Date.distantPast

    func applicationDidFinishLaunching(_ notification: Notification) {
        configureMenu()
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

        let appMenu = NSMenu()
        appMenu.addItem(
            withTitle: "Open Dashboard",
            action: #selector(openDashboard(_:)),
            keyEquivalent: "o"
        )
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(
            withTitle: "Quit Wealthsimple Prospector",
            action: #selector(quitApp(_:)),
            keyEquivalent: "q"
        )

        appMenu.items.forEach { $0.target = self }
        appMenuItem.submenu = appMenu
        NSApp.mainMenu = mainMenu
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
