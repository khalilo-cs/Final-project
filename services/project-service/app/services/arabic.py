"""Arabic number agreement: 1 and 2 have their own forms, 3-10 take the plural,
11 and above take the singular (accusative where the sentence needs it)."""


def count_phrase(n: int, one: str, two: str, few: str, many: str) -> str:
    if n == 1:
        return one
    if n == 2:
        return two
    if 3 <= n % 100 <= 10:
        return f"{n} {few}"
    return f"{n} {many}"
