import re

_RE = re.compile(r"^[vV]?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


def parse(text):
    """'v1.2.3-beta.1+build' -> (1, 2, 3, ('beta', '1')); None if not SemVer."""
    m = _RE.match((text or "").strip())
    if not m:
        return None
    major, minor, patch, pre = m.groups()
    return int(major), int(minor), int(patch), tuple(pre.split(".")) if pre else ()


def _key(v):
    major, minor, patch, pre = v
    if not pre:
        return major, minor, patch, (1,)            # a release outranks any pre-release
    ids = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre)
    return major, minor, patch, (0, ids)


def is_newer(candidate, current):
    a, b = parse(candidate), parse(current)
    return bool(a and b) and _key(a) > _key(b)
