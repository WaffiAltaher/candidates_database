import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCRIPT = """
import logging
import container.main
logging.getLogger("helpers").debug("debug-marker")
logging.getLogger("helpers").info("info-marker")
"""


def _run(level):
    env = dict(os.environ)
    env.update(
        AUTH_SECRET="test-secret-that-is-long-enough-123",
        ALLOWED_ORIGIN="*",
        PYTHONPATH=ROOT,
    )
    if level is None:
        env.pop("LOG_LEVEL", None)
    else:
        env["LOG_LEVEL"] = level
    proc = subprocess.run(
        [sys.executable, "-c", SCRIPT], env=env, cwd=ROOT, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stderr


@pytest.mark.parametrize("level", [None, "INFO"])
def test_info_level_suppresses_debug(level):
    out = _run(level)
    assert "info-marker" in out
    assert "debug-marker" not in out


def test_debug_level_emits_debug():
    assert "debug-marker" in _run("DEBUG")


def test_no_print_in_main():
    with open(os.path.join(ROOT, "container", "main.py")) as f:
        assert "print(" not in f.read()
