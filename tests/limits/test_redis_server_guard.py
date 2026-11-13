"""Guards the redis_server tests themselves: they must fail, never skip, without a server URL.

This test is not marked, so the default run executes it. CI always sets the URL, so only this
test would notice the missing-URL path turning into a skip or a silent pass.
"""

import os
import subprocess
import sys
from pathlib import Path

URL_VARIABLE = "TOLLGATE_TEST_REDIS_URL"
ROOT = Path(__file__).resolve().parents[2]


def test_the_redis_server_tests_fail_and_name_the_variable_when_it_is_unset() -> None:
    environment = {name: value for name, value in os.environ.items() if name != URL_VARIABLE}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-m", "redis_server", "-rs", "-p", "no:cacheprovider"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert URL_VARIABLE in output
    assert "45 failed" in output
    assert "skipped" not in output
    assert "passed" not in output
