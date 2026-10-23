import Foundation

struct GuardError: Error, CustomStringConvertible {
    let description: String
    init(_ message: String) { description = message }
}

struct Policy: Codable {
    var sites: [String: [String]]
    // Optional only so the installer can read and remove a legacy policy's domains.
    var passages: [Passage]?
    var defaultMinutes: Int
    var maxMinutes: Int

    func validate() throws {
        guard (1...120).contains(maxMinutes),
              (1...maxMinutes).contains(defaultMinutes), !sites.isEmpty else {
            throw GuardError("Invalid policy limits.")
        }
        guard let passages, !passages.isEmpty else {
            throw GuardError("Missing educational passages. Rebuild and reinstall FocusGuard.")
        }
        var passageIDs = Set<String>()
        for passage in passages {
            try passage.validate()
            guard passageIDs.insert(passage.id).inserted else { throw GuardError("Duplicate passage ID.") }
        }
        var seen = Set<String>()
        for (site, domains) in sites {
            guard site.range(of: "^[a-z][a-z0-9-]{0,39}$", options: .regularExpression) != nil,
                  !domains.isEmpty else { throw GuardError("Invalid site name or empty domain list.") }
            for domain in domains {
                guard domain.count <= 253, domain == domain.lowercased(), domain.contains("."),
                      domain.split(separator: ".", omittingEmptySubsequences: false).allSatisfy({
                          $0.count <= 63 && $0.range(of: "^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", options: .regularExpression) != nil
                      }), seen.insert(domain).inserted else {
                    throw GuardError("Invalid or duplicate domain: \(domain)")
                }
            }
        }
    }

    var domains: Set<String> { Set(sites.values.flatMap { $0 }) }
}

struct Grant: Codable {
    var expires: Double
    var remaining: Double
}

struct GuardState: Codable {
    var grants: [String: Grant] = [:]
    var observedAt: Double

    // A rollback of the wall clock closes all exceptions. Monotonic elapsed time
    // (including sleep) additionally prevents repeated small clock edits in-process.
    mutating func advance(now: Double, elapsed: Double, policy: Policy) {
        if now < observedAt - 1 { grants.removeAll() }
        for site in Array(grants.keys) {
            guard var grant = grants[site], policy.sites[site] != nil,
                  grant.expires.isFinite, grant.remaining.isFinite else {
                grants.removeValue(forKey: site)
                continue
            }
            grant.remaining = min(grant.remaining - max(0, elapsed), grant.expires - now, Double(policy.maxMinutes * 60))
            if grant.remaining <= 0 { grants.removeValue(forKey: site) }
            else { grants[site] = grant }
        }
        observedAt = now
    }

    mutating func unlock(site: String, minutes: Int, now: Double, policy: Policy) throws {
        guard policy.sites[site] != nil, (1...policy.maxMinutes).contains(minutes) else {
            throw GuardError("Unknown site or duration outside 1...\(policy.maxMinutes) minutes.")
        }
        guard grants[site] == nil else { throw GuardError("Already unlocked; lock it before requesting another exception.") }
        grants[site] = Grant(expires: now + Double(minutes * 60), remaining: Double(minutes * 60))
    }
}

enum Hosts {
    static let begin = "# BEGIN FOCUSGUARD MANAGED BLOCK"
    static let end = "# END FOCUSGUARD MANAGED BLOCK"

    static func render(_ text: String, policy: Policy, grants: [String: Grant], enabled: Bool = true) throws -> String {
        // Remove our marked block and any mappings for owned domains elsewhere.
        // Preserve every unrelated hostname, even on a shared mapping line.
        let lines = text.components(separatedBy: "\n")
        let starts = lines.indices.filter { lines[$0] == begin }
        let ends = lines.indices.filter { lines[$0] == end }
        guard starts.count <= 1, ends.count <= 1,
              starts.count == ends.count,
              starts.isEmpty || starts[0] < ends[0] else {
            throw GuardError("Damaged FocusGuard hosts markers; refusing to discard unrelated content.")
        }
        var output: [String] = []
        for (index, line) in lines.enumerated() {
            if let first = starts.first, let last = ends.first, (first...last).contains(index) { continue }
            let parts = line.split(separator: "#", maxSplits: 1, omittingEmptySubsequences: false)
            let fields = parts[0].split(whereSeparator: { $0.isWhitespace }).map(String.init)
            guard fields.count >= 2 else { output.append(line); continue }
            let kept = fields.dropFirst().filter { !policy.domains.contains($0.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))) }
            if kept.count == fields.count - 1 { output.append(line) }
            else if !kept.isEmpty {
                output.append(fields[0] + "\t" + kept.joined(separator: " ") + (parts.count == 2 ? " #" + parts[1] : ""))
            } else if parts.count == 2 { output.append("#" + parts[1]) }
        }
        while output.last == "" { output.removeLast() }
        if enabled {
            output += ["", begin]
            for site in policy.sites.keys.sorted() where grants[site] == nil {
                for domain in policy.sites[site]!.sorted() {
                    output.append("0.0.0.0 \(domain)")
                    output.append("::1 \(domain)")
                }
            }
            output.append(end)
        }
        return output.joined(separator: "\n") + "\n"
    }
}
