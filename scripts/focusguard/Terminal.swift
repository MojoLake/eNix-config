import Foundation
import Darwin

func continuousSeconds() -> Double {
    var info = mach_timebase_info_data_t()
    mach_timebase_info(&info)
    return Double(mach_continuous_time()) * Double(info.numer) / Double(info.denom) / 1_000_000_000
}

private func terminalWidth() -> Int {
    var size = winsize()
    if ioctl(STDOUT_FILENO, TIOCGWINSZ, &size) == 0, size.ws_col > 0 { return max(20, Int(size.ws_col)) }
    return 80
}

// Read raw terminal input directly: buffered stdio can retain input across the
// reason/challenge boundary. Escape sequences are editing events, not failures.
private func editedLine(validate: (String) -> String?) throws -> String {
    var input: [Character] = []
    var cursor = 0
    var utf8: [UInt8] = []
    var escape: [UInt8]? = nil
    var pasting = false
    var pasteTail: [UInt8] = []
    let pasteEnd = Array("\u{001B}[201~".utf8)

    func columns(_ character: Character) -> Int {
        // The process can start in the C locale, where wcwidth returns -1 for
        // printable non-ASCII punctuation. Never treat those glyphs as zero width.
        character.unicodeScalars.map {
            let width = Int(wcwidth(wchar_t($0.value)))
            return width < 0 ? 1 : width
        }.max() ?? 1
    }
    func render() {
        let width = max(10, terminalWidth() - 4)
        // Keep the insertion point visible, including when editing a long line.
        var start = cursor
        var before = 0
        while start > 0 && before + columns(input[start - 1]) < width {
            start -= 1
            before += columns(input[start])
        }
        var end = start
        var used = 0
        while end < input.count && used + columns(input[end]) <= width {
            used += columns(input[end])
            end += 1
        }
        print("\r\u{001B}[2K> " + String(input[start..<end]), terminator: "")
        print("\r\u{001B}[\(2 + before)C", terminator: "")
        fflush(stdout)
    }
    func moveWord(_ direction: Int) {
        if direction < 0 {
            while cursor > 0 && input[cursor - 1].isWhitespace { cursor -= 1 }
            while cursor > 0 && !input[cursor - 1].isWhitespace { cursor -= 1 }
        } else {
            while cursor < input.count && !input[cursor].isWhitespace { cursor += 1 }
            while cursor < input.count && input[cursor].isWhitespace { cursor += 1 }
        }
    }
    func handleEscape(_ bytes: [UInt8]) {
        let sequence = String(decoding: bytes, as: UTF8.self)
        switch sequence {
        case "[D", "OD": cursor = max(0, cursor - 1)
        case "[C", "OC": cursor = min(input.count, cursor + 1)
        case "[H", "OH", "[1~", "[7~": cursor = 0
        case "[F", "OF", "[4~", "[8~": cursor = input.count
        case "[3~":
            if cursor < input.count { input.remove(at: cursor) }
        case "b", "[1;3D", "[1;5D": moveWord(-1)
        case "f", "[1;3C", "[1;5C": moveWord(1)
        case "[200~": pasting = true; pasteTail.removeAll()
        default: break // Up/down, Escape, and unsupported keys are harmless.
        }
        render()
    }
    render()
    while true {
        if escape != nil {
            // A standalone Escape or incomplete sequence must not swallow the
            // next ordinary key indefinitely. Real split sequences can arrive
            // across several read() calls within this inter-byte timeout.
            var descriptor = pollfd(fd: STDIN_FILENO, events: Int16(POLLIN), revents: 0)
            let available = poll(&descriptor, 1, 150)
            if available == 0 { escape = nil; continue }
            if available < 0 {
                if errno == EINTR { continue }
                throw GuardError("Cannot read terminal input.")
            }
        }
        var byte: UInt8 = 0
        let count = read(STDIN_FILENO, &byte, 1)
        if count < 0 && errno == EINTR { continue }
        guard count == 1 else { throw GuardError("Input closed.") }
        if byte == 3 { throw GuardError("Canceled.") }
        if pasting {
            // Drain the entire bracketed paste, including newlines and escape
            // sequences, without changing typed text or submitting a line.
            pasteTail.append(byte)
            pasteTail = Array(pasteTail.suffix(pasteEnd.count))
            if pasteTail == pasteEnd {
                pasting = false
                pasteTail.removeAll()
                print("\nPaste ignored. Your typing and progress are unchanged.")
                render()
            }
            continue
        }
        if var sequence = escape {
            if byte == 27 { escape = []; continue }
            sequence.append(byte)
            if sequence.count == 1 && (byte == 91 || byte == 79) {
                escape = sequence
            } else if sequence.count == 1 || (0x40...0x7e).contains(byte) {
                escape = nil
                handleEscape(sequence)
            } else if sequence.count > 32 {
                escape = nil
            } else { escape = sequence }
            continue
        }
        if byte == 27 { utf8.removeAll(); escape = []; continue }
        if byte == 127 || byte == 8 {
            utf8.removeAll()
            if cursor > 0 { cursor -= 1; input.remove(at: cursor) }
            render()
            continue
        }
        if byte == 4 {
            if cursor < input.count { input.remove(at: cursor) }
            render()
            continue
        }
        if byte == 1 { cursor = 0; render(); continue }
        if byte == 5 { cursor = input.count; render(); continue }
        if byte == 21 { input.removeAll(); cursor = 0; utf8.removeAll(); render(); continue }
        if byte == 10 || byte == 13 {
            // Arrival timing cannot reliably distinguish paste from fast typing
            // or buffered input. Only explicit bracketed paste is discarded.
            let text = String(input)
            if let error = validate(text) {
                print("\n" + error)
                render()
            } else { print(""); return text }
            continue
        }
        if byte == 9 { byte = 32 }
        guard byte >= 32 else { continue }
        utf8.append(byte)
        guard let character = String(bytes: utf8, encoding: .utf8) else {
            if utf8.count >= 4 { utf8.removeAll() }
            continue
        }
        utf8.removeAll()
        if input.count < 2048 {
            let characters = Array(character)
            input.insert(contentsOf: characters, at: cursor)
            cursor += characters.count
        }
        render()
    }
}

func challenge(_ passage: Passage, recall: Recall) throws {
    guard isatty(STDIN_FILENO) == 1, isatty(STDOUT_FILENO) == 1 else {
        throw GuardError("Unlock requires an interactive terminal.")
    }
    var original = termios()
    guard tcgetattr(STDIN_FILENO, &original) == 0 else { throw GuardError("Cannot read terminal settings.") }
    var raw = original
    raw.c_lflag &= ~tcflag_t(ICANON | ECHO | ISIG)
    guard tcsetattr(STDIN_FILENO, TCSAFLUSH, &raw) == 0 else { throw GuardError("Cannot configure terminal.") }
    // Alternate screen keeps the passage out of normal scrollback for recall.
    print("\u{001B}[?1049h\u{001B}[?2004h", terminator: "")
    fflush(stdout)
    defer {
        tcsetattr(STDIN_FILENO, TCSAFLUSH, &original)
        print("\u{001B}[?2004l\u{001B}[?1049l", terminator: "")
        fflush(stdout)
    }
    var completedWords = 0
    for (paragraphIndex, paragraph) in passage.paragraphs.enumerated() {
        let lines = wrappedLines(paragraph, width: max(16, min(68, terminalWidth() - 6)))
        for (lineIndex, line) in lines.enumerated() {
            print("\u{001B}[2J\u{001B}[H", terminator: "")
            print("\(passage.title) | \(passage.topic) | \(passage.wordCount) words")
            print("Paragraph \(paragraphIndex + 1)/\(passage.paragraphs.count), line \(lineIndex + 1)/\(lines.count) | \(completedWords)/\(passage.wordCount) words complete")
            print("Type the line, then Enter. Arrows move; Backspace edits; Ctrl-U clears; Ctrl-C cancels.")
            print("Case, punctuation and extra spaces are flexible. Pasted text is ignored.\n")
            for contextLine in lines { print(contextLine) }
            print("\nType this line:\n\(line)")
            let expected = normalizedWords(line)
            _ = try editedLine { typed in
                let actual = normalizedWords(typed)
                guard actual != expected else { return nil }
                let mismatch = zip(actual, expected).prefix { $0 == $1 }.count
                if mismatch < expected.count {
                    return "Check word \(mismatch + 1): expected '\(expected[mismatch])'. Backspace to edit, or Ctrl-U to clear this line."
                }
                return "Extra words at the end. Backspace to edit this line."
            }
            completedWords += line.split(whereSeparator: \.isWhitespace).count
        }
    }
    print("\u{001B}[2J\u{001B}[H", terminator: "")
    print("Passage complete. Recall without looking back:\n\n\(recall.question)")
    print("Write a short answer, or 'skip' to reveal the explanation. This is not graded.")
    _ = try editedLine { $0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Try an answer, or type 'skip'." : nil }
    print("\nSelf-check:\n\(recall.answer)")
    print("\nFurther reading:")
    for source in passage.sources { print(source) }
    print("\nPress Enter to finish and unlock.")
    _ = try editedLine { _ in nil }
}
