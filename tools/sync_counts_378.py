"""Round 19 final count sync: 378 tests (unit 235, integration 58).

Run once from the service root:  python3 tools/sync_counts_378.py
"""
import io


def sub(path, pairs):
    s = io.open(path, encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, (path, old[:70])
        s = s.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8").write(s)


sub("README.md", [("with 377 passing", "with 378 passing"), ("# 377 tests", "# 378 tests")])

sub("docs/TESTING.md", [
    ("| **Total** | | **377 passing** |", "| **Total** | | **378 passing** |"),
    ("explanation builder**) | **234** —", "explanation builder**) | **235** —"),
    ("`test_explanation_engine.py` (34) pins", "`test_explanation_engine.py` (35) pins"),
])

sub("IMPLEMENTATION_REPORT.md", [
    ("**377/377 automated tests passing", "**378/378 automated tests passing"),
    ("| 29 | pytest suites incl. mocks, no paid credentials | **Yes** | 377 tests, offline |",
     "| 29 | pytest suites incl. mocks, no paid credentials | **Yes** | 378 tests, offline |"),
    ("pytest -q                 # 377 passed", "pytest -q                 # 378 passed"),
])
print("counts synced to 378 (unit 235, integration 58)")
