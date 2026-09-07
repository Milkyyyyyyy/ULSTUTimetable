"""
Валидация и нормализация названий групп УлГТУ.
"""

import re

def normalize_group(group: str) -> str:
    """Нормализует название группы: убирает пробелы вокруг дефиса, приводит к верхнему регистру."""
    group = group.strip()
    group = re.sub(r"\s*-\s*", "-", group)
    group = re.sub(r"\s+", "", group)

    return group.upper()