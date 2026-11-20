"""Read integers as Vietnamese words (canonical spelling).

Canonical form uses "một / bốn / năm / linh / nghìn"; the colloquial variants
("mốt / tư / lăm / lẻ / ngàn") are folded into it by ``normalize``.
"""

from __future__ import annotations

DIGITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
SCALES = ["", "nghìn", "triệu"]


def _read_triple(n: int, full: bool) -> list[str]:
    """Read 0..999. ``full`` = a higher group precedes, so hundreds are always read."""
    hundreds, rest = divmod(n, 100)
    tens, units = divmod(rest, 10)
    words: list[str] = []
    if hundreds or full:
        words += [DIGITS[hundreds], "trăm"]
    if tens == 0:
        if units:
            if words:
                words.append("linh")
            words.append(DIGITS[units])
    elif tens == 1:
        words.append("mười")
        if units:
            words.append(DIGITS[units])
    else:
        words += [DIGITS[tens], "mươi"]
        if units:
            words.append(DIGITS[units])
    return words


def number_to_words(n: int) -> str:
    if n < 0 or n >= 10**9:
        raise ValueError(f"number out of range: {n}")
    if n == 0:
        return DIGITS[0]
    groups: list[int] = []
    while n:
        n, g = divmod(n, 1000)
        groups.append(g)
    words: list[str] = []
    for idx in range(len(groups) - 1, -1, -1):
        g = groups[idx]
        if g == 0:
            continue
        words += _read_triple(g, full=bool(words))
        if SCALES[idx]:
            words.append(SCALES[idx])
    return " ".join(words)
