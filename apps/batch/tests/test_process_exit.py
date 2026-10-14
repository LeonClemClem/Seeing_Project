import subprocess
import sys


def test_clean_interpreter_exit():
    """Regression: eccodes loaded before psycopg segfaulted at exit (code 139)."""
    code = "import seeing_batch.cli, seeing_batch.arome, eccodes, psycopg; print('ok')"
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
