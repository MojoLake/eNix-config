import Foundation
import Darwin

@main
struct TerminalTest {
    static func main() {
        let recall = Recall(question: "Why keep a cache?", answer: "It avoids repeating earlier work.")
        var passage = Passage(id: "fixture", topic: "Testing", title: "Editable prose",
                              paragraphs: ["Cache bytes: 13.5 KiB, not 135 KiB.", "Read once; reuse often.", "Don't repeat earlier work."],
                              recalls: [recall, recall], sources: ["https://example.com/reference"])
        do {
            if CommandLine.arguments.count > 1 {
                passage = try JSONDecoder().decode([Passage].self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))[0]
            }
            // Include the production reason-to-raw-input transition.
            print("Reason?", terminator: " "); fflush(stdout)
            guard readLine() != nil else { throw GuardError("Missing reason") }
            try challenge(passage, recall: recall)
            print("ACCEPTED")
        }
        catch { print("REJECTED: \(error)"); exit(1) }
    }
}
