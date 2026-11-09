"""
Comprehensive Test Runner for Week 3
Runs all rule tests (BR-01 to BR-17), edge case tests (EC-01 to EC-08),
and end-to-end integration tests without requiring third-party dependencies.
"""

import sys
import tempfile
from pathlib import Path

# Add src and tests to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src"))
sys.path.insert(0, str(BASE_DIR / "tests"))

import test_rules
import test_edge_cases
import test_integration


def run_test_func(func, tmp_dir):
    """Run a test function, injecting tmp_path if expected."""
    import inspect
    sig = inspect.signature(func)
    if "tmp_path" in sig.parameters:
        return func(tmp_dir)
    return func()


def main():
    print("=" * 80)
    print("  PS-082 Carbon Exchange Registry & Settlement Engine — Week 3 Test Suite")
    print("=" * 80)

    modules = [
        ("Business Rules (BR-01 to BR-17)", test_rules),
        ("Explicit Edge Cases (EC-01 to EC-08)", test_edge_cases),
        ("Full Integration & Output Contract", test_integration),
    ]

    total_passed = 0
    total_failed = 0
    failures = []

    for category, mod in modules:
        print(f"\n--- Running: {category} ---")
        test_funcs = [
            (name, getattr(mod, name))
            for name in dir(mod)
            if name.startswith("test_") and callable(getattr(mod, name))
        ]

        for name, func in test_funcs:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                try:
                    run_test_func(func, tmp_path)
                    print(f"  [PASS] {name}")
                    total_passed += 1
                except Exception as e:
                    print(f"  [FAIL] {name}: {e}")
                    total_failed += 1
                    failures.append((name, e))

    print("\n" + "=" * 80)
    print(f"  Summary: {total_passed} PASSED, {total_failed} FAILED (Total: {total_passed + total_failed})")
    print("=" * 80)

    if failures:
        print("\nFailures:")
        for name, err in failures:
            print(f"  - {name}: {err}")
        sys.exit(1)
    else:
        print("\nAll Week 3 verification checks passed successfully!")
        sys.exit(0)


if __name__ == "__main__":
    main()
