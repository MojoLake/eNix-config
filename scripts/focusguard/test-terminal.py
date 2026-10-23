"""Exercise the real terminal editor in a disposable PTY; never unlock a site."""
import fcntl
import os
import pty
import re
import select
import struct
import subprocess
import sys
import termios
import time


def case(kind):
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 30 if kind == 'narrow' else 80, 0, 0))
    before = termios.tcgetattr(slave)
    command = [sys.argv[1]] + ([sys.argv[2]] if kind == 'full' else [])
    proc = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave)
    pending = b''
    transcript = b''

    def until(pattern):
        nonlocal pending, transcript
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            match = re.search(pattern, pending)
            if match:
                pending = pending[match.end():]
                return match
            if select.select([master], [], [], 0.1)[0]:
                data = os.read(master, 65536)
                pending += data
                transcript += data
        raise AssertionError((kind, pattern, transcript[-3000:]))

    def type_text(text):
        for index, char in enumerate(text):
            # Include pairs closer than the former 15 ms limit.
            time.sleep((0.001 if index % 2 else 0.025) if kind == 'fast_pairs' else 0.012)
            os.write(master, char.encode())

    try:
        until(rb'Reason\? ')
        os.write(master, b'An educational test\n')
        target = until(rb'Type this line:\r?\n([^\r\n]+)').group(1).decode()
        until(rb'> ')
        if kind == 'cancel':
            os.write(master, b'\x03')
            until(rb'REJECTED:')
        elif kind in ('full', 'narrow'):
            line_count = 0
            while True:
                type_text(target)
                os.write(master, b'\n')
                line_count += 1
                next_part = until(rb'Type this line:\r?\n([^\r\n]+)|Passage complete\. Recall without looking back:')
                if next_part.group(1) is None:
                    break
                target = next_part.group(1).decode()
                until(rb'> ')
            assert line_count > 3, 'wrapped lines were not exercised'
            until(rb'> ')
            type_text('skip')
            os.write(master, b'\n')
            until(rb'Press Enter to finish and unlock\.')
            until(rb'> ')
            os.write(master, b'\n')
            until(rb'ACCEPTED')
        else:
            if kind == 'paste':
                prefix = target[:10]
                type_text(prefix)
                os.write(master, b'\x1b[200~unwanted\ntext\x1b[D')
                # The end marker may be split across reads.
                for byte in b'\x1b[201~':
                    os.write(master, bytes([byte]))
                    time.sleep(0.01)
                until(rb'Paste ignored\. Your typing and progress are unchanged\.')
                until(re.escape(b'\x1b[2K> ' + prefix.encode()))
                type_text(target[10:])
            elif kind == 'burst':
                os.write(master, target.encode())
            elif kind in ('arrows', 'split_arrows'):
                type_text(target.replace('13.5', '13.6'))
                position = target.index('13.5') + 3
                for _ in range(len(target) - position):
                    if kind == 'split_arrows':
                        for byte in b'\x1b[D':
                            os.write(master, bytes([byte]))
                            time.sleep(0.01)
                    else:
                        os.write(master, b'\x1b[D')
                os.write(master, b'\x1b[3~')
                type_text('5')
                os.write(master, b'\x1b[C' * (len(target) - position - 1))
            elif kind == 'home_end':
                type_text(target[1:])
                os.write(master, b'\x1bOH')
                type_text(target[0])
                os.write(master, b'\x1bOF\x04')  # Ctrl-D at end is harmless.
            elif kind == 'control_edit':
                type_text('X' + target[1:])
                os.write(master, b'\x01\x04')  # Ctrl-A, forward delete.
                type_text(target[0])
                os.write(master, b'\x05')
            elif kind == 'word_move':
                type_text('Cache Xbytes: ' + target.split(': ', 1)[1])
                os.write(master, b'\x1b[H\x1bf\x1b[3~\x1b[F')
            elif kind == 'escape':
                os.write(master, b'\x1b[A\x1b[B\x1b[99~\x1b')
                time.sleep(0.2)
                type_text(target)
            elif kind == 'edit':
                type_text('Cache bytes: 13.6')
                os.write(master, b'\n')
                until(rb'Check word 3')
                os.write(master, b'\x7f')
                type_text('5 KiB, not 135 KiB.')
            elif kind == 'clear':
                type_text('Incorrect words')
                os.write(master, b'\x15')
                type_text(target)
            else:
                type_text('cache   BYTES 13.5 kib not 135 kib' if kind == 'flexible' else target)
            os.write(master, b'\n')
            for paragraph in (2, 3):
                until(f'Paragraph {paragraph}/3'.encode())
                target = until(rb'Type this line:\r?\n([^\r\n]+)').group(1).decode()
                until(rb'> ')
                if kind == 'flexible' and paragraph == 3:
                    target = target.replace("Don't", 'Don’t')
                if kind == 'later_paste' and paragraph == 2:
                    type_text(target[:5])
                    os.write(master, b'\x1b[200~first line\nsecond line\x1b[201~')
                    until(rb'Paste ignored\. Your typing and progress are unchanged\.')
                    until(re.escape(b'\x1b[2K> ' + target[:5].encode()))
                    type_text(target[5:])
                    assert transcript.count(b'Paragraph 1/3') == 1, 'completed progress was lost'
                else:
                    type_text(target)
                if kind == 'flexible' and paragraph == 3:
                    # A curly apostrophe still occupies a terminal column in
                    # the default C locale used by the executable.
                    until(re.escape(target.encode() + f'\r\x1b[{len(target) + 2}C'.encode()))
                os.write(master, b'\n')
            until(rb'Passage complete\. Recall without looking back:')
            assert b'\x1b[2J\x1b[H' in transcript, 'passage was not cleared'
            until(rb'> ')
            if kind == 'cancel_recall':
                os.write(master, b'\x03')
                until(rb'REJECTED:')
            else:
                os.write(master, b'\n')
                until(rb'Try an answer, or type')
                type_text('skip' if kind == 'skip' else 'It saves computation')
                os.write(master, b'\n')
                until(rb'Self-check:')
                until(rb'Press Enter to finish and unlock\.')
                until(rb'> ')
                os.write(master, b'\n')
                until(rb'ACCEPTED')
        proc.wait(timeout=5)
        rejected = kind in ('cancel', 'cancel_recall')
        assert proc.returncode == (1 if rejected else 0), (kind, transcript[-2000:])
        assert termios.tcgetattr(slave) == before, 'terminal settings not restored'
        assert b'\x1b[?1049l' in transcript, 'alternate screen not restored'
        assert b'\x1b[?2004l' in transcript, 'paste mode not restored'
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        os.close(master)
        os.close(slave)


cases = ('typed', 'edit', 'clear', 'flexible', 'fast_pairs', 'skip', 'paste', 'burst', 'cancel', 'cancel_recall', 'full', 'narrow', 'arrows', 'split_arrows', 'home_end', 'control_edit', 'word_move', 'escape', 'later_paste')
for kind in cases:
    case(kind)
print(f'PASS: {len(cases)} terminal checks; editing, progress, recall, input rejection, and terminal restoration.')
