import re

def normalize_group(group: str) -> str:
    group = group.strip()
    group = re.sub(r"\s*-\s*", "-", group)
    group = re.sub(r"\s+", "", group)

    return group.upper()