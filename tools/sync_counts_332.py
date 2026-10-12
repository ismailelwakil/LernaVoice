"""Round 18 final count sync: 332 tests (unit 200, integration 47).

Run once from the service root:  python3 tools/sync_counts_332.py
"""
import io


def read(p):
    return io.open(p, encoding="utf-8").read()


def write(p, s):
    io.open(p, "w", encoding="utf-8").write(s)


def sub(path, pairs):
    s = read(path)
    for old, new in pairs:
        assert old in s, (path, old[:70])
        s = s.replace(old, new, 1)
    write(path, s)


sub("README.md", [
    ("with 324 passing", "with 332 passing"),
    ("# 324 tests", "# 332 tests"),
])

sub("docs/TESTING.md", [
    ("**Arabic's fusHa register and the Egyptian aliases that normalise to it**) | **199**",
     "**Arabic's fusHa register, the Egyptian aliases that normalise to it, and the request shape that accepts them**) | **200**"),
    ("| **Total** | | **324 passing** |", "| **Total** | | **332 passing** |"),
    ("`test_arabic_dialects.py` (23) pins the formal register",
     "`test_arabic_dialects.py` (24) pins the formal register"),
])

sub("IMPLEMENTATION_REPORT.md", [
    ("**324/324 automated tests passing", "**332/332 automated tests passing"),
    ("| 29 | pytest suites incl. mocks, no paid credentials | **Yes** | 324 tests, offline |",
     "| 29 | pytest suites incl. mocks, no paid credentials | **Yes** | 332 tests, offline |"),
    ("# 324 passed", "# 332 passed"),
    ("concept store. Tests: `test_arabic_dialects.py` (23) |",
     "concept store. Tests: `test_arabic_dialects.py` (24) + `test_arabic_session_request.py` (7) |"),
])
print("counts synced to 332")
