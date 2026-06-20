"""A deterministic, zero-cost threat scanner.

Run before any harvested text is written into memory that later enters the
system prompt. This is a regex backstop, not a model call — it catches the
obvious poisoning vectors (prompt-injection, role/template injection,
pipe-to-shell, secret exfiltration, invisible/bidi unicode) for free.
"""

from __future__ import annotations

import re

# Invisible / bidi code-point ranges, specified by HEX so the source contains
# no literal invisible characters (which would be unreadable and would trip the
# scanner on itself). The character class is assembled at import time.
_INVISIBLE_RANGES: tuple[tuple[int, int], ...] = (
    (0x200B, 0x200F),  # zero-width space .. right-to-left mark
    (0x202A, 0x202E),  # bidi embedding / override
    (0x2066, 0x2069),  # bidi isolates
    (0xFEFF, 0xFEFF),  # BOM / zero-width no-break space
)
_INVISIBLE = re.compile("[" + "".join(f"{chr(lo)}-{chr(hi)}" for lo, hi in _INVISIBLE_RANGES) + "]")

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "prompt_injection",
        re.compile(
            r"(ignore|disregard|forget)\s+(?:\w+\s+){0,3}(instructions|prompts?|context|rules?)",
            re.I,
        ),
    ),
    ("role_injection", re.compile(r"</?(system|assistant|user|tool)\s*>", re.I)),
    ("chat_template", re.compile(r"<\|(im_start|im_end|endoftext)\|>")),
    ("pipe_to_shell", re.compile(r"\b(curl|wget)\b[^\n|]*\|\s*(sh|bash|zsh)\b", re.I)),
    (
        "exfiltration",
        re.compile(r"(ANTHROPIC_API_KEY|AWS_SECRET_ACCESS_KEY|BEGIN [A-Z ]*PRIVATE KEY)"),
    ),
    ("invisible_unicode", _INVISIBLE),
)


def scan(text: str) -> list[str]:
    """Return the names of every tripped rule (empty list = clean). Pure."""
    return [name for name, pattern in _RULES if pattern.search(text)]


def is_safe(text: str) -> bool:
    return not scan(text)
