import Foundation
import Darwin

let directory = "/Library/Application Support/FocusGuard"
let label = "local.focusguard"
let plistPath = "/Library/LaunchDaemons/local.focusguard.plist"
let runtime = Runtime(directory: directory, hostsPath: "/etc/hosts")

func serviceLoaded() throws -> Bool {
    try run("/bin/launchctl", ["print", "system/" + label], allowFailure: true, quiet: true) == 0
}

func requireService() throws {
    guard try serviceLoaded() else { throw GuardError("Service is not loaded. Run focusguard install first.") }
}

func stopService() throws {
    if try serviceLoaded() { try run("/bin/launchctl", ["bootout", "system/" + label]) }
}

func install(policyPath: String) throws {
    let data = try Data(contentsOf: URL(fileURLWithPath: policyPath))
    let policy = try JSONDecoder().decode(Policy.self, from: data)
    try policy.validate()
    var st = stat()
    guard lstat(runtime.hostsPath, &st) == 0, (st.st_mode & S_IFMT) == S_IFREG else {
        throw GuardError("Hosts is not a regular file; resolve its ownership with your existing configuration first.")
    }
    let hostsMode = st.st_mode & 0o777
    let hostsOwner = (st.st_uid, st.st_gid)
    let hosts = try String(contentsOfFile: runtime.hostsPath, encoding: .utf8)
    _ = try Hosts.render(hosts, policy: policy, grants: [:])
    let binary = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[0]))
    if lstat(directory, &st) == 0 {
        guard (st.st_mode & S_IFMT) == S_IFDIR, st.st_uid == 0, st.st_mode & 0o022 == 0 else {
            throw GuardError("Existing installation directory must be a root-owned, non-writable directory.")
        }
    } else { try FileManager.default.createDirectory(atPath: directory, withIntermediateDirectories: false) }
    chmod(directory, 0o755)
    let wasLoaded = try serviceLoaded()
    let targets: [(String, mode_t)] = [
        (runtime.path("focusguard"), 0o755), (runtime.path("policy.json"), 0o644),
        (runtime.path("state.json"), 0o600), (plistPath, 0o644), (runtime.hostsPath, hostsMode)
    ]
    // Snapshot before changing anything. Errors during activation restore these
    // files and reload the previous service, rather than leaving a half-install.
    var previous: [String: Data] = [:]
    try stopService()
    do {
      try runtime.withLock {
        for (path, _) in targets {
            if FileManager.default.fileExists(atPath: path) {
                guard lstat(path, &st) == 0, (st.st_mode & S_IFMT) == S_IFREG else {
                    throw GuardError("Refusing to replace non-regular installation file: \(path)")
                }
                previous[path] = try Data(contentsOf: URL(fileURLWithPath: path))
            }
        }
      }
    } catch {
        if wasLoaded { _ = try? run("/bin/launchctl", ["bootstrap", "system", plistPath]) }
        throw error
    }
    do {
      try runtime.withLock {
        let hosts = String(decoding: previous[runtime.hostsPath]!, as: UTF8.self)
        if !FileManager.default.fileExists(atPath: runtime.path("hosts.before-install")) {
            try runtime.write(Data(hosts.utf8), to: runtime.path("hosts.before-install"))
        }
        // Remove mappings for previously configured domains when updating the policy.
        if let oldData = previous[runtime.path("policy.json")],
           let old = try? JSONDecoder().decode(Policy.self, from: oldData) {
            let clean = try Hosts.render(hosts, policy: old, grants: [:], enabled: false)
            try runtime.write(Data(clean.utf8), to: runtime.hostsPath, mode: hostsMode)
        }
        try runtime.write(binary, to: runtime.path("focusguard"), mode: 0o755)
        try runtime.write(data, to: runtime.path("policy.json"), mode: 0o644)
        try runtime.save(GuardState(observedAt: Date().timeIntervalSince1970))
        let plist: [String: Any] = [
            "Label": label, "ProgramArguments": [runtime.path("focusguard"), "daemon"],
            "RunAtLoad": true, "KeepAlive": true, "ThrottleInterval": 10,
            "UserName": "root", "Umask": 0o077,
            "StandardOutPath": runtime.path("service.log"), "StandardErrorPath": runtime.path("service.log")
        ]
        try runtime.write(PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0), to: plistPath, mode: 0o644)
      }
      try runtime.tick()
      try run("/bin/launchctl", ["bootstrap", "system", plistPath])
    } catch {
        let installError = error
        try stopService()
        try runtime.withLock {
            for (path, mode) in targets {
                if let original = previous[path] { try runtime.write(original, to: path, mode: mode) }
                else if FileManager.default.fileExists(atPath: path) { try FileManager.default.removeItem(atPath: path) }
            }
            chown(runtime.hostsPath, hostsOwner.0, hostsOwner.1)
        }
        _ = try? run("/usr/bin/dscacheutil", ["-flushcache"])
        _ = try? run("/usr/bin/killall", ["-HUP", "mDNSResponder"])
        if wasLoaded { try run("/bin/launchctl", ["bootstrap", "system", plistPath]) }
        throw GuardError("Installation failed; previous files restored: \(installError)")
    }
    print("FocusGuard installed and blocking. Previous hosts saved at \(runtime.path("hosts.before-install")).")
}

func main() throws {
    let args = Array(CommandLine.arguments.dropFirst())
    guard let command = args.first, command != "help", command != "--help" else {
        print("""
        FocusGuard — local website blocking with deliberate exceptions
          focusguard install                 Build/install the Nix-configured policy (administrator access)
          focusguard status                  Show blocks and temporary exceptions
          focusguard unlock youtube [20]     Educational passage + recall; duration in minutes
          focusguard lock [youtube]          End one or all exceptions immediately
          focusguard uninstall               Stop service and remove managed hosts entries
        """)
        return
    }
    guard geteuid() == 0 else { throw GuardError("Administrator access required. Use the focusguard wrapper or sudo.") }
    switch command {
    case "install":
        guard args.count == 2 else { throw GuardError("Internal install requires a policy path. Use the Nix wrapper: focusguard install") }
        try install(policyPath: args[1])
    case "daemon":
        let daemonLock = open(runtime.path("daemon.lock"), O_CREAT | O_RDWR | O_NOFOLLOW, 0o600)
        guard daemonLock >= 0, flock(daemonLock, LOCK_EX | LOCK_NB) == 0 else {
            throw GuardError("Another FocusGuard daemon is already running.")
        }
        defer { close(daemonLock) }
        var last = continuousSeconds()
        while true {
            let now = continuousSeconds()
            do { try runtime.tick(elapsed: now - last) }
            catch { fputs("FocusGuard: \(error)\n", stderr) }
            last = now
            Thread.sleep(forTimeInterval: 2)
        }
    case "status":
        try requireService()
        try runtime.withLock {
            let policy = try runtime.policy()
            let now = Date().timeIntervalSince1970
            var state = runtime.state(now: now)
            state.advance(now: now, elapsed: max(0, now - state.observedAt), policy: policy)
            for site in policy.sites.keys.sorted() {
                if let grant = state.grants[site] {
                    print("\(site): allowed until \(ISO8601DateFormatter().string(from: Date(timeIntervalSince1970: grant.expires)))")
                } else { print("\(site): blocked") }
            }
        }
        print("Service loaded. Policy: \(runtime.path("policy.json"))")
    case "unlock":
        guard (2...3).contains(args.count) else { throw GuardError("Usage: focusguard unlock SITE [MINUTES]") }
        let policy = try runtime.policy()
        let site = args[1]
        let minutes = args.count == 3 ? Int(args[2]) : policy.defaultMinutes
        guard policy.sites[site] != nil, let minutes, (1...policy.maxMinutes).contains(minutes) else {
            throw GuardError("Choose \(policy.sites.keys.sorted().joined(separator: ", ")) and 1...\(policy.maxMinutes) minutes.")
        }
        // Do not grant access without a running service to expire it.
        try requireService()
        guard isatty(STDIN_FILENO) == 1 else { throw GuardError("An interactive terminal is required.") }
        // Hold a separate lock while typing; the daemon must keep expiring grants.
        let challengeLock = open(runtime.path("challenge.lock"), O_CREAT | O_RDWR | O_NOFOLLOW, 0o600)
        guard challengeLock >= 0 else { throw GuardError("Cannot open challenge lock.") }
        defer { close(challengeLock) }
        guard flock(challengeLock, LOCK_EX | LOCK_NB) == 0 else {
            throw GuardError("Another unlock challenge is already open. Finish or cancel it first.")
        }
        defer { flock(challengeLock, LOCK_UN) }
        let (passage, recall) = try runtime.withLock {
            let now = Date().timeIntervalSince1970
            var state = runtime.state(now: now)
            state.advance(now: now, elapsed: max(0, now - state.observedAt), policy: policy)
            guard state.grants[site] == nil else { throw GuardError("Already unlocked; lock it before requesting another exception.") }
            var learning = try runtime.learning()
            let selection = learning.next(in: policy.passages!)
            try runtime.saveLearning(learning)
            return selection
        }
        print("Why do you need \(site) for \(minutes) minutes? ", terminator: "")
        fflush(stdout)
        guard let reason = readLine()?.trimmingCharacters(in: .whitespacesAndNewlines),
              (10...1000).contains(reason.count) else { throw GuardError("Enter a reason of 10–1000 characters.") }
        try challenge(passage, recall: recall)
        try requireService()
        try runtime.withLock {
            let currentPolicy = try runtime.policy()
            guard try runtime.encoder.encode(currentPolicy) == runtime.encoder.encode(policy) else { throw GuardError("Policy changed; request again.") }
            let now = Date().timeIntervalSince1970
            var state = runtime.state(now: now)
            state.advance(now: now, elapsed: max(0, now - state.observedAt), policy: policy)
            try state.unlock(site: site, minutes: minutes, now: now, policy: policy)
            try runtime.audit(site: site, reason: reason, minutes: minutes)
            try runtime.save(state)
            try runtime.apply(policy: policy, state: state)
            var learning = try runtime.learning()
            learning.complete(passage.id)
            try runtime.saveLearning(learning)
        }
        print("\(site) allowed for \(minutes) minutes. Restart the browser if it cached the block.")
    case "lock":
        guard args.count <= 2 else { throw GuardError("Usage: focusguard lock [SITE]") }
        try requireService()
        try runtime.withLock {
            let policy = try runtime.policy()
            var state = runtime.state(now: Date().timeIntervalSince1970)
            if args.count == 2 {
                guard policy.sites[args[1]] != nil else { throw GuardError("Unknown site.") }
                state.grants.removeValue(forKey: args[1])
            } else { state.grants.removeAll() }
            try runtime.save(state)
            try runtime.apply(policy: policy, state: state)
        }
        print("Blocked again.")
    case "uninstall":
        let policy = try runtime.policy()
        try stopService()
        try runtime.withLock {
            try runtime.apply(policy: policy, state: GuardState(observedAt: 0), enabled: false)
            if FileManager.default.fileExists(atPath: plistPath) { try FileManager.default.removeItem(atPath: plistPath) }
        }
        print("Service removed and sites unblocked. Backup and logs retained at \(directory).")
    default: throw GuardError("Unknown command. Run focusguard help.")
    }
}

do { try main() }
catch { fputs("FocusGuard: \(error)\n", stderr); exit(1) }
