"""Round 19 count sync: 377 tests (unit 234, integration 58).

Run once from the service root:  python3 tools/sync_counts_377.py
"""
import io


def sub(path, pairs):
    s = io.open(path, encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, (path, old[:70])
        s = s.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8").write(s)


sub("README.md", [
    ("with 332 passing", "with 377 passing"),
    ("# 332 tests", "# 377 tests"),
])

sub("docs/TESTING.md", [
    ("**Arabic's fusHa register, the Egyptian aliases that normalise to it, and the request "
     "shape that accepts them**) | **200** —",
     "**Arabic's fusHa register, the Egyptian aliases that normalise to it, and the request "
     "shape that accepts them**, **the levels, the vetted sources and the explanation builder**) "
     "| **234** —"),
    ("`test_arabic_dialects.py` (24) pins the formal register",
     "`test_explanation_engine.py` (34) pins the round-19 layer: level spellings, what each "
     "level demands, the vetted packs, the move order per level, the closing question staying "
     "last, the grounded prompt block, the Arabic moves carrying their English original, the "
     "profile round-trip and the request > LERNA > store > default precedence; "
     "`test_arabic_dialects.py` (24) pins the formal register"),
    ("curriculum API + session plans | 40 |",
     "curriculum API + session plans, **the grounded explanation over REST and the socket** | 58 |"),
    ("| **Total** | | **332 passing** |", "| **Total** | | **377 passing** |"),
])

sub("IMPLEMENTATION_REPORT.md", [
    ("**332/332 automated tests passing", "**377/377 automated tests passing"),
    ("| 29 | pytest suites incl. mocks, no paid credentials | **Yes** | 332 tests, offline |",
     "| 29 | pytest suites incl. mocks, no paid credentials | **Yes** | 377 tests, offline |"),
    ("pytest -q                 # 332 passed", "pytest -q                 # 377 passed"),
])
print("counts synced to 377 (unit 234, integration 58)")
