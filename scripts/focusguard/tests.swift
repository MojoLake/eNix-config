import Foundation
import Darwin

@main
struct Tests {
    static var passed = 0
    static func check(_ condition: @autoclosure () throws -> Bool, _ message: String) throws {
        guard try condition() else { throw GuardError("FAIL: \(message)") }
        passed += 1
    }

    static func rejects(_ message: String, _ action: () throws -> Void) throws {
        do { try action() }
        catch { passed += 1; return }
        throw GuardError("FAIL: expected rejection: \(message)")
    }

    static func main() throws {
        let passages = try JSONDecoder().decode([Passage].self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
        try check(passages.count == 30 && Set(passages.map(\.topic)).count == 6, "30 passages across six topics")
        let policy = Policy(sites: ["youtube": ["youtube.com", "www.youtube.com"], "x": ["x.com"]],
                            passages: passages, defaultMinutes: 20, maxMinutes: 30)
        try policy.validate()
        try check(normalizedWords("Don't  cache—twice!") == normalizedWords("don’t cache twice."), "prose punctuation, case and whitespace")
        try check(normalizedWords("13.5 KiB") != normalizedWords("135 KiB"), "decimal values remain distinct")
        try check(normalizedWords("read the cache") != normalizedWords("read cache"), "missing words rejected")
        var rotation = LearningState()
        var firstQuestions: [String: String] = [:]
        var previousID: String?
        for cycle in 0..<2 {
            var seen = Set<String>()
            for index in 0..<passages.count {
                let (passage, recall) = rotation.next(in: passages)
                try check(seen.insert(passage.id).inserted, "no repeats within cycle")
                if index == 0, cycle > 0 { try check(passage.id != previousID, "no repeat at cycle boundary") }
                let restored = try JSONDecoder().decode(LearningState.self, from: JSONEncoder().encode(rotation))
                var resumed = restored
                try check(resumed.next(in: passages).0.id == passage.id, "cancel/restart retains pending passage")
                if cycle == 0 { firstQuestions[passage.id] = recall.question }
                else { try check(firstQuestions[passage.id] != recall.question, "recall question changes on repeat") }
                rotation.complete(passage.id)
                previousID = passage.id
            }
        }
        var invalidPolicy = policy
        invalidPolicy.passages = nil
        try rejects("missing passages") { try invalidPolicy.validate() }
        invalidPolicy.passages = passages + [passages[0]]
        try rejects("duplicate passage IDs") { try invalidPolicy.validate() }
        var shortPassage = passages[0]
        shortPassage.paragraphs = ["Too short."]
        try rejects("short passage") { try shortPassage.validate() }
        var injectedPassage = passages[0]
        injectedPassage.title += "\u{001B}[2J"
        try rejects("terminal control sequence") { try injectedPassage.validate() }
        let legacy = Data(#"{"sites":{"x":["x.com"]},"challengeLength":200,"defaultMinutes":20,"maxMinutes":30}"#.utf8)
        let legacyPolicy = try JSONDecoder().decode(Policy.self, from: legacy)
        try check(legacyPolicy.domains == ["x.com"], "legacy domains readable for install migration")
        var bad = policy
        bad.sites["x"] = ["x.com\n127.0.0.1 evil"]
        try rejects("host injection") { try bad.validate() }
        bad = policy; bad.sites["x"] = ["youtube.com"]
        try rejects("duplicate hosts") { try bad.validate() }
        bad = policy; bad.defaultMinutes = 31
        try rejects("invalid limits") { try bad.validate() }

        let original = "# Local entries\n127.0.0.1 localhost\n::1 localhost\n10.0.0.2 internal.verda.test\n0.0.0.0 youtube.com unrelated.test # keep this comment\n0.0.0.0 x.com\n"
        let blocked = try Hosts.render(original, policy: policy, grants: [:])
        try check(blocked.contains("10.0.0.2 internal.verda.test"), "keep corporate entry")
        try check(blocked.contains("0.0.0.0\tunrelated.test # keep this comment"), "keep mixed-line aliases/comment")
        try check(blocked.contains("::1 www.youtube.com"), "IPv6 blocked")
        try check(Hosts.render(blocked, policy: policy, grants: [:]) == blocked, "idempotent render")
        let granted = ["youtube": Grant(expires: 100, remaining: 60)]
        let open = try Hosts.render(blocked, policy: policy, grants: granted)
        try check(!open.contains("youtube.com"), "remove all owned aliases during exception")
        try check(open.contains("0.0.0.0 x.com"), "other site stays blocked")
        let tampered = blocked.replacingOccurrences(of: "0.0.0.0 x.com", with: "# 0.0.0.0 x.com")
        try check(Hosts.render(tampered, policy: policy, grants: [:]) == blocked, "repair commented-out block")
        let restored = try Hosts.render(original + "1.2.3.4 X.COM. other.test\n", policy: policy, grants: [:])
        try check(restored.contains("1.2.3.4\tother.test"), "remove conflicting case/trailing-dot alias")
        let removed = try Hosts.render(blocked, policy: policy, grants: [:], enabled: false)
        try check(!removed.contains("FOCUSGUARD") && !removed.contains("x.com") && removed.contains("internal.verda.test"), "uninstall preserves unrelated mappings")
        try rejects("damaged markers") { _ = try Hosts.render(blocked.replacingOccurrences(of: Hosts.end, with: ""), policy: policy, grants: [:]) }

        var state = GuardState(observedAt: 100)
        try state.unlock(site: "youtube", minutes: 1, now: 100, policy: policy)
        try rejects("overlong duration") { try state.unlock(site: "x", minutes: 31, now: 100, policy: policy) }
        try rejects("unknown site") { try state.unlock(site: "evil", minutes: 1, now: 100, policy: policy) }
        try rejects("extend without relocking") { try state.unlock(site: "youtube", minutes: 1, now: 100, policy: policy) }
        state.advance(now: 159, elapsed: 59, policy: policy)
        try check(state.grants["youtube"] != nil, "exception before expiry")
        state.advance(now: 160, elapsed: 1, policy: policy)
        try check(state.grants.isEmpty, "expiry at exact boundary")
        try state.unlock(site: "youtube", minutes: 1, now: 160, policy: policy)
        state.advance(now: 10, elapsed: 1, policy: policy)
        try check(state.grants.isEmpty, "clock rollback closes exception")
        try state.unlock(site: "x", minutes: 1, now: 10, policy: policy)
        state.advance(now: 11, elapsed: 61, policy: policy)
        try check(state.grants.isEmpty, "monotonic expiry includes sleep")

        let temp = FileManager.default.temporaryDirectory.appendingPathComponent("focusguard-tests-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: temp, withIntermediateDirectories: false)
        defer { try? FileManager.default.removeItem(at: temp) }
        let runtime = Runtime(directory: temp.path, hostsPath: temp.appendingPathComponent("hosts").path, flushDNS: false)
        try runtime.saveLearning(rotation)
        try check(runtime.learning().visits.count == 30, "learning history persists independently of grants")
        try runtime.write(Data(original.utf8), to: runtime.hostsPath, mode: 0o644)
        try runtime.write(runtime.encoder.encode(policy), to: runtime.path("policy.json"))
        try runtime.tick(now: 100)
        try check(String(contentsOfFile: runtime.hostsPath, encoding: .utf8) == blocked, "filesystem enforcement")
        state = GuardState(observedAt: 100)
        try state.unlock(site: "youtube", minutes: 1, now: 100, policy: policy)
        try runtime.save(state)
        // A fresh Runtime simulates a daemon restart loading persisted exceptions.
        let restarted = Runtime(directory: temp.path, hostsPath: runtime.hostsPath, flushDNS: false)
        try restarted.tick(now: 110)
        try check(!String(contentsOfFile: runtime.hostsPath, encoding: .utf8).contains("youtube.com"), "restart retains valid exception")
        try restarted.tick(now: 161)
        try check(String(contentsOfFile: runtime.hostsPath, encoding: .utf8) == blocked, "restart expires exception")
        try runtime.write(Data("broken state".utf8), to: runtime.path("state.json"))
        try runtime.write(Data(original.utf8), to: runtime.hostsPath, mode: 0o644)
        try runtime.tick(now: 162)
        try check(String(contentsOfFile: runtime.hostsPath, encoding: .utf8) == blocked, "corruption fails closed")
        try runtime.audit(site: "youtube", reason: "A lecture\nwith a newline", minutes: 20)
        let log = try Data(contentsOf: URL(fileURLWithPath: runtime.path("requests.jsonl")))
        try check((try JSONSerialization.jsonObject(with: log) as? [String: Any])?["minutes"] as? Int == 20, "valid audit JSON")
        try FileManager.default.removeItem(atPath: runtime.hostsPath)
        try FileManager.default.createSymbolicLink(atPath: runtime.hostsPath, withDestinationPath: runtime.path("policy.json"))
        try rejects("hosts symlink") { try runtime.tick(now: 163) }
        print("PASS: \(passed) checks; only temporary files were modified.")
    }
}
