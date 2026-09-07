import re

PATTERN = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\Z")

def precedence(value):
    match = PATTERN.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise ValueError("invalid version")
    major, minor, patch, prerelease, build = match.groups()
    identifiers = []
    if prerelease is not None:
        for identifier in prerelease.split("."):
            if identifier.isascii() and identifier.isdigit():
                if len(identifier) > 1 and identifier.startswith("0"):
                    raise ValueError("invalid version")
                identifiers.append((0, int(identifier)))
            else:
                identifiers.append((1, identifier))
    return (int(major), int(minor), int(patch), prerelease is None, tuple(identifiers), build or "")

def order(values):
    if not isinstance(values, list):
        raise ValueError("invalid version list")
    return sorted(values, key=precedence)
