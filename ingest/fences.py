"""Find fenced code blocks in Markdown so the cleaner and chunker can leave them alone."""
import re

_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def fence_mask(lines: list[str]) -> list[bool]:
    """True for every line inside a fenced code block, delimiters included.

    A block closes only on the same fence character, at least as long as the opening one.
    A fence that is never closed is not a fence: it must not swallow the rest of the page.
    """
    mask = [False] * len(lines)
    i = 0
    while i < len(lines):
        m = _OPEN.match(lines[i])
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            marker = m.group(1)
            close = re.compile(rf"^ {{0,3}}{re.escape(marker[0])}{{{len(marker)},}}[ \t]*$")
            end = next((k for k in range(i + 1, len(lines)) if close.match(lines[k])), None)
            if end is not None:
                for k in range(i, end + 1):
                    mask[k] = True
                i = end + 1
                continue
        i += 1
    return mask
