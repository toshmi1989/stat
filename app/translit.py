"""Uzbek Cyrillic -> Uzbek Latin (the script of the questionnaire). Latin text passes through unchanged, so it is safe to apply twice."""
import re

_LOW = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
        "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "s", "ч": "ch", "ш": "sh", "ъ": "’", "ь": "", "э": "e", "ю": "yu", "я": "ya", "ў": "o‘", "қ": "q", "ғ": "g‘", "ҳ": "h"}
_CYR = re.compile("[А-Яа-яЁёЎўҚқҒғҲҳ]")


def lat(s) -> str:
    if not s or not _CYR.search(str(s)):
        return s if isinstance(s, str) else ("" if s is None else str(s))
    s = str(s)
    out = []
    for i, ch in enumerate(s):
        lo = ch.lower()
        if lo not in _LOW:
            out.append(ch)
            continue
        if lo == "е" and (i == 0 or not s[i - 1].isalpha() or s[i - 1] in "ъЪ"):
            m = "ye"
        elif lo == "ц" and (i == 0 or not s[i - 1].isalpha()):
            m = "ts"
        else:
            m = _LOW[lo]
        if ch != lo and m:
            nxt = s[i + 1] if i + 1 < len(s) else ""
            m = m.upper() if (nxt and nxt.isupper() and len(m) > 1) else m[0].upper() + m[1:]
        out.append(m)
    return "".join(out)
