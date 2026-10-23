import Foundation
import Darwin

final class Runtime {
    let directory: String
    let hostsPath: String
    let flushDNS: Bool
    var pendingDNS = true
    let encoder = JSONEncoder()

    init(directory: String, hostsPath: String, flushDNS: Bool = true) {
        self.directory = directory
        self.hostsPath = hostsPath
        self.flushDNS = flushDNS
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    }

    func path(_ name: String) -> String { directory + "/" + name }

    func write(_ data: Data, to path: String, mode: mode_t = 0o600) throws {
        try data.write(to: URL(fileURLWithPath: path), options: .atomic)
        guard chmod(path, mode) == 0 else { throw GuardError("Cannot set permissions: \(path)") }
    }

    func withLock<T>(_ action: () throws -> T) throws -> T {
        let fd = open(path("lock"), O_CREAT | O_RDWR | O_NOFOLLOW, 0o600)
        guard fd >= 0 else { throw GuardError("Cannot open service lock. Install FocusGuard first.") }
        defer { close(fd) }
        guard flock(fd, LOCK_EX) == 0 else { throw GuardError("Cannot acquire service lock.") }
        defer { flock(fd, LOCK_UN) }
        return try action()
    }

    func policy() throws -> Policy {
        let value = try JSONDecoder().decode(Policy.self, from: Data(contentsOf: URL(fileURLWithPath: path("policy.json"))))
        try value.validate()
        return value
    }

    func state(now: Double) -> GuardState {
        // Corrupt/missing state closes exceptions; it never lifts the block.
        (try? JSONDecoder().decode(GuardState.self, from: Data(contentsOf: URL(fileURLWithPath: path("state.json")))))
            ?? GuardState(observedAt: now)
    }

    func save(_ state: GuardState) throws { try write(encoder.encode(state), to: path("state.json")) }

    func learning() throws -> LearningState {
        guard FileManager.default.fileExists(atPath: path("learning.json")) else { return LearningState() }
        return try JSONDecoder().decode(LearningState.self, from: Data(contentsOf: URL(fileURLWithPath: path("learning.json"))))
    }

    func saveLearning(_ state: LearningState) throws {
        try write(encoder.encode(state), to: path("learning.json"))
    }

    func apply(policy: Policy, state: GuardState, enabled: Bool = true) throws {
        var st = stat()
        guard lstat(hostsPath, &st) == 0, (st.st_mode & S_IFMT) == S_IFREG else {
            throw GuardError("Hosts must be a regular file; refusing to replace a symlink or missing file.")
        }
        let current = try String(contentsOfFile: hostsPath, encoding: .utf8)
        let desired = try Hosts.render(current, policy: policy, grants: state.grants, enabled: enabled)
        if current != desired {
            // Abort if another editor changed the file while we generated it.
            guard try String(contentsOfFile: hostsPath, encoding: .utf8) == current else {
                throw GuardError("Hosts changed concurrently; retrying on the next service tick.")
            }
            try write(Data(desired.utf8), to: hostsPath, mode: st.st_mode & 0o777)
            if geteuid() == 0 { guard chown(hostsPath, st.st_uid, st.st_gid) == 0 else { throw GuardError("Cannot preserve hosts ownership.") } }
            pendingDNS = true
        }
        if pendingDNS && flushDNS {
            try run("/usr/bin/dscacheutil", ["-flushcache"])
            try run("/usr/bin/killall", ["-HUP", "mDNSResponder"])
        }
        pendingDNS = false
    }

    func tick(now: Double = Date().timeIntervalSince1970, elapsed: Double? = nil) throws {
        try withLock {
            let policy = try self.policy()
            var state = self.state(now: now)
            let hadGrants = !state.grants.isEmpty
            state.advance(now: now, elapsed: elapsed ?? max(0, now - state.observedAt), policy: policy)
            if hadGrants { try save(state) }
            try apply(policy: policy, state: state)
        }
    }

    func audit(site: String, reason: String, minutes: Int) throws {
        let record: [String: Any] = ["date": ISO8601DateFormatter().string(from: Date()), "site": site,
                                    "reason": reason, "minutes": minutes]
        var data = try JSONSerialization.data(withJSONObject: record, options: .sortedKeys)
        data.append(0x0A)
        let fd = open(path("requests.jsonl"), O_WRONLY | O_APPEND | O_CREAT | O_NOFOLLOW, 0o600)
        guard fd >= 0 else { throw GuardError("Cannot open request log.") }
        defer { close(fd) }
        try data.withUnsafeBytes { raw in
            guard Darwin.write(fd, raw.baseAddress, raw.count) == raw.count else { throw GuardError("Cannot append request log.") }
        }
    }
}

@discardableResult
func run(_ executable: String, _ arguments: [String], allowFailure: Bool = false, quiet: Bool = false) throws -> Int32 {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: executable)
    process.arguments = arguments
    if quiet {
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
    }
    try process.run()
    process.waitUntilExit()
    if process.terminationStatus != 0 && !allowFailure {
        throw GuardError("\(executable) exited with status \(process.terminationStatus)")
    }
    return process.terminationStatus
}
