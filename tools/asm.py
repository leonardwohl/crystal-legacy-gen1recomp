"""Small helpers for reading pokecrystal-style RGBDS data files.

These are not an assembler. They understand just enough of the data macros
used under data/ (db/dw/dn rows, a few named macros, labels, `percent`) to
turn the tables Crystal Legacy edits into Python values.
"""

import os
import re


def strip_comment(line):
    """Drop a trailing `;` comment, ignoring semicolons inside strings."""
    out, in_str = [], False
    for ch in line:
        if ch == '"':
            in_str = not in_str
        elif ch == ";" and not in_str:
            break
        out.append(ch)
    return "".join(out).rstrip()


def read_lines(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return [strip_comment(l) for l in fh.read().splitlines()]


def split_args(text):
    """Split a macro argument list on commas outside of strings."""
    args, cur, in_str = [], [], False
    for ch in text:
        if ch == '"':
            in_str = not in_str
        if ch == "," and not in_str:
            args.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    tail = "".join(cur).strip()
    if tail or args:
        args.append(tail)
    return args


def statements(path):
    """Yield (label, None) or (op, args) for each meaningful line."""
    for raw in read_lines(path):
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^([.\w]+):{1,2}\s*(.*)$", line)
        if m and not line.startswith(("db ", "dw ", "dn ")):
            yield ("label", m.group(1))
            line = m.group(2).strip()
            if not line:
                continue
        parts = line.split(None, 1)
        op = parts[0]
        yield (op, split_args(parts[1]) if len(parts) > 1 else [])


_NUM = re.compile(r"\$[0-9a-fA-F]+|%[01]+|\d+")


def evaluate(expr, consts=None):
    """Evaluate a numeric RGBDS expression such as `70 percent + 1`."""
    consts = consts or {}
    e = expr.strip()
    if e in consts:
        return consts[e]
    e = e.replace("percent", "* 255 // 100")

    def num(m):
        t = m.group(0)
        if t.startswith("$"):
            return str(int(t[1:], 16))
        if t.startswith("%"):
            return str(int(t[1:], 2))
        return t

    e = _NUM.sub(num, e)
    e = re.sub(r"\b[A-Za-z_]\w*\b", lambda m: str(consts[m.group(0)])
               if m.group(0) in consts else m.group(0), e)
    if not re.fullmatch(r"[\d\s+\-*/()]+", e):
        raise ValueError("cannot evaluate %r" % expr)
    return int(eval(e, {"__builtins__": {}}))  # digits and operators only


def const_list(path, start_marker=None):
    """Names declared with `const` in order (const_def resets are ignored)."""
    out = []
    for op, args in statements(path):
        if op == "const" and args:
            out.append(args[0])
    return out


def species_order(root):
    names = []
    for op, args in statements(os.path.join(root, "constants/pokemon_constants.asm")):
        if op == "const" and args:
            if args[0] == "EGG" or args[0].startswith("NUM_"):
                break
            names.append(args[0])
    # The first block of consts is the 251 species; stop at the egg marker.
    return names[:251]


def const_values(path):
    """{NAME: value} honouring const_def / const_skip / const_next."""
    out, value = {}, 0
    for op, args in statements(path):
        if op == "const_def":
            value = evaluate(args[0]) if args and args[0] else 0
        elif op == "const_skip":
            value += evaluate(args[0]) if args and args[0] else 1
        elif op == "const_next":
            value = evaluate(args[0])
        elif op == "const" and args:
            out[args[0]] = value
            value += 1
    return out
