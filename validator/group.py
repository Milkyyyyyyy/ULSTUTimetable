import re


GROUP_PATTERN = re.compile(
    r"^[А-ЯЁа-яё]+-\d{2}$"
)

def is_group_valid(group: str) -> bool|None:
	return GROUP_PATTERN.fullmatch(group)

def normalize_group(group: str) -> str:
    group = group.strip()
    group = re.sub(r"\s*-\s*", "-", group)
    group = re.sub(r"\s+", "", group)

    return group.upper()