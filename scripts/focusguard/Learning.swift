import Foundation

struct Recall: Codable {
    var question: String
    var answer: String
}

struct Passage: Codable {
    var id: String
    var topic: String
    var title: String
    var paragraphs: [String]
    var recalls: [Recall]
    var sources: [String]

    var wordCount: Int { paragraphs.joined(separator: " ").split(whereSeparator: \.isWhitespace).count }

    func validate() throws {
        let strings = [id, topic, title] + paragraphs + recalls.flatMap { [$0.question, $0.answer] } + sources
        guard !id.isEmpty, !title.isEmpty, !topic.isEmpty,
              (200...300).contains(wordCount), (3...6).contains(paragraphs.count),
              recalls.count >= 2, !sources.isEmpty,
              strings.allSatisfy({ !$0.isEmpty && !$0.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }) }),
              sources.allSatisfy({ URL(string: $0)?.scheme == "https" }) else {
            throw GuardError("Invalid educational passage: \(id)")
        }
    }
}

// Case, spacing and punctuation do not determine whether the prose was typed.
// Keep decimal points between digits: 1.5 and 15 are different numbers.
func normalizedWords(_ text: String) -> [String] {
    let chars = Array(text.lowercased())
    var result = ""
    for (index, char) in chars.enumerated() {
        if char.isLetter || char.isNumber { result.append(char) }
        else if char == "'" || char == "’" { continue }
        else if char == ".", index > 0, index + 1 < chars.count,
                chars[index - 1].isNumber, chars[index + 1].isNumber { result.append(char) }
        else { result.append(" ") }
    }
    return result.split(whereSeparator: \.isWhitespace).map(String.init)
}

func wrappedLines(_ text: String, width: Int) -> [String] {
    var lines: [String] = []
    for word in text.split(whereSeparator: \.isWhitespace) {
        if let last = lines.last, last.count + 1 + word.count <= width {
            lines[lines.count - 1] += " " + word
        } else { lines.append(String(word)) }
    }
    return lines
}

struct LearningState: Codable {
    var known: [String] = []
    var remaining: [String] = []
    var visits: [String: Int] = [:]
    var lastID: String?

    mutating func next(in passages: [Passage]) -> (Passage, Recall) {
        let ids = passages.map(\.id).sorted()
        if known != ids || remaining.isEmpty || Set(remaining).count != remaining.count || !Set(remaining).isSubset(of: Set(ids)) {
            known = ids
            remaining = ids.shuffled()
            if remaining.count > 1, remaining.first == lastID { remaining.swapAt(0, 1) }
        }
        let passage = passages.first { $0.id == remaining[0] }!
        let visit = max(0, visits[passage.id, default: 0])
        return (passage, passage.recalls[visit % passage.recalls.count])
    }

    mutating func complete(_ id: String) {
        remaining.removeAll { $0 == id }
        visits[id] = (max(0, visits[id, default: 0]) % 1_000_000) + 1
        lastID = id
    }
}
