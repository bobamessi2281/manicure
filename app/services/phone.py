from __future__ import annotations

import re


def normalize_phone(raw: str) -> str:
    """
    Нормализация телефона: только цифры, ведущая 7 для РФ.
    Примеры: +7 999 123-45-67 -> 79991234567, 8999... -> 7999...
    """
    digits = re.sub(r"\D+", "", raw or "")
    if not digits:
        return ""
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if digits.startswith("9") and len(digits) == 10:
        digits = "7" + digits
    if not digits.startswith("7") and len(digits) == 11 and digits[0] in "789":
        digits = "7" + digits[1:]
    return digits
