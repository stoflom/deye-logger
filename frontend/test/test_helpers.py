#!/usr/bin/env python3
"""
Shared test harness for the frontend UI tests (frontend/test) — issue #96.

Every test script builds one TestResult, records checks with
`t.check(condition, desc)` and ends with `sys.exit(t.summary())`, so each
run finishes with a single unambiguous verdict:

  ✅ TESTS PASSED — <n>/<n> checks passed
  or
  ❌ TESTS FAILED — <n>/<m> checks passed, <k> failed
  Failed checks:
    - <desc>
    - ...

The process exit code always reflects the verdict (0 = pass, 1 = fail).
"""

import sys


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failures = []

    def check(self, condition: bool, desc: str, detail: str = ""):
        if condition:
            self.passed += 1
            print(f"  ✓ {desc}")
            return True
        self.failed += 1
        self.failures.append(desc)
        print(f"  ✗ {desc}" + (f" — {detail}" if detail else ""))
        return False

    def summary(self) -> int:
        """Print the final verdict and return the process exit code."""
        total = self.passed + self.failed
        rule = "=" * 70
        print("\n" + rule)
        if self.failed:
            print(f"❌ TESTS FAILED — {self.passed}/{total} checks passed, {self.failed} failed")
            print("Failed checks:")
            for f in self.failures:
                print(f"  - {f}")
            print(rule)
            return 1
        print(f"✅ TESTS PASSED — {self.passed}/{total} checks passed")
        print(rule)
        return 0


def finish(t: "TestResult") -> None:
    """Print the final verdict and exit with the matching code."""
    sys.exit(t.summary())
