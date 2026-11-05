"""Compile pokecrystal text blocks into gen1recomp's Crystal text strings.

gen1recomp stores each text as one string: a line break is "\\n" (line/next),
a new paragraph "\\f" (para), a scrolled continuation "\\v" (cont), and the
end is "{DONE}" or "{PROMPT}". Name slots become {PLAYER} / {RIVAL}. This
mirrors RomExtractorGen2:decodeGen2Text, so compiled text reads exactly like
text gen1recomp imported from the ROM.
"""

import re

from asm import read_lines

OPENERS = {"text": "", "line": "\n", "next": "\n", "para": "\f", "cont": "\v"}
CLOSERS = {"done": "{DONE}", "prompt": "{PROMPT}"}
SYMBOLS = [("<PLAYER>", "{PLAYER}"), ("<PLAY_G>", "{PLAYER}"), ("<RIVAL>", "{RIVAL}"),
           ("<PK><MN>", "PKMN"), ("<……>", "……"), ("#", "POKé"), ("<PKMN>", "PKMN")]


def _string(s):
    s = s.strip()
    if not (s.startswith('"') and s.endswith('"')):
        raise ValueError("expected a string, got %r" % s)
    s = s[1:-1]
    for a, b in SYMBOLS:
        s = s.replace(a, b)
    return s.rstrip("@")


def text_blocks(path):
    """{label: compiled string} for every text block in an .asm file."""
    out, cur, parts = {}, None, []

    def close(final):
        nonlocal cur, parts
        if cur:
            out[cur] = "".join(parts) + final
        cur, parts = None, []

    for raw in read_lines(path):
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^([A-Za-z_][\w.]*):{1,2}$", line)
        if m:
            if cur and parts:
                close("")  # a label with no terminator yet: text_far chains etc.
            cur, parts = m.group(1), []
            continue
        if cur is None:
            continue
        op, _, rest = line.partition(" ")
        if op in OPENERS and rest.strip().startswith('"'):
            parts.append(OPENERS[op] + _string(rest))
        elif op in CLOSERS:
            close(CLOSERS[op])
        elif op == "text_ram" or op == "text_decimal":
            parts.append("{STRBUF}" if op == "text_ram" else "{NUM}")
        elif op == "text_end":
            close("")
        elif op == "text_far":
            # A pointer to shared text elsewhere; not followed here.
            cur, parts = None, []
        else:
            # Not a text block (a script or data label); discard.
            cur, parts = None, []
    return out
