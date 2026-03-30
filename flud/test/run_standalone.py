#!/usr/bin/env python3

import subprocess
import sys
from pathlib import Path


TEST_SEQUENCE = [
    "FludPrimitiveTestFailure.py",
]


def main():
    test_dir = Path(__file__).resolve().parent
    args = sys.argv[1:]

    for index, test_name in enumerate(TEST_SEQUENCE, start=1):
        test_path = test_dir / test_name
        print(f"[{index}/{len(TEST_SEQUENCE)}] running {test_name}")
        completed = subprocess.run([sys.executable, str(test_path), *args])
        if completed.returncode != 0:
            print(f"{test_name} failed with exit code {completed.returncode}")
            return completed.returncode

    print("all standalone tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
