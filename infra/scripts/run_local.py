"""Run the website on this computer: FastAPI on :8000 and Vite on :5173 (live reload).

By default the data comes from the shared **dev** database on GCP, reached through an IAP tunnel
(`gcloud compute start-iap-tunnel`), so you see real forecasts. `--db local` uses the Postgres of
`docker compose` instead (`make db-up migrate dev-seed`).

Works on Windows, macOS and Linux with only the standard library:

    python infra/scripts/run_local.py --install   # first time (installs the dependencies)
    python infra/scripts/run_local.py             # then open http://localhost:5173

Ctrl+C stops everything. This script never changes the database schema: the dev database is
migrated only by the "Deploy to dev" workflow.
"""

import argparse
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
API_DIR = ROOT / "apps" / "api"
WEB_DIR = ROOT / "apps" / "web"

DEFAULT_PROJECT = "project-astrarome"
DEFAULT_ZONE = "us-central1-a"
DEFAULT_DB_VM = "seeing-db"
DEFAULT_TUNNEL_PORT = 15432
DEV_DB = "seeing_dev"  # database and role; laptops can only reach dev (pg_hba)
DEV_DB_SECRET = "db-password-dev"  # noqa: S105 (Secret Manager id, not a password)
LOCAL_DATABASE_URL = "postgresql+psycopg://seeing:seeing@localhost:5432/seeing_dev"
API_PORT = 8000  # apps/web/vite.config.ts proxies /api to this port
WEB_PORT = 5173  # Vite's port, set in apps/web/vite.config.ts
TUNNEL_TIMEOUT_S = 60

IS_WINDOWS = os.name == "nt"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run the Seeing website locally (API + live-reloading frontend).")
    parser.add_argument(
        "--db", choices=["dev", "local"], default="dev", help="dev: shared dev database on GCP (default); local: docker"
    )
    parser.add_argument("--install", action="store_true", help="install Python and Node dependencies first")
    parser.add_argument("--project", default=DEFAULT_PROJECT, type=gcp_name, help="GCP project")
    parser.add_argument("--zone", default=DEFAULT_ZONE, type=gcp_name, help="zone of the database VM")
    parser.add_argument("--db-vm", default=DEFAULT_DB_VM, type=gcp_name, help="name of the database VM")
    parser.add_argument("--tunnel-port", type=int, default=DEFAULT_TUNNEL_PORT, help="local port of the IAP tunnel")
    return parser.parse_args(argv)


def fail(message: str) -> None:
    """Print a plain-language error and exit."""
    print(f"\nERROR: {message}\n", file=sys.stderr)
    sys.exit(1)


def gcp_name(value: str) -> str:
    """argparse type: a GCP project / zone / VM name (also keeps cmd.exe from seeing odd characters)."""
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", value):
        raise argparse.ArgumentTypeError(f"invalid name: {value!r}")
    return value


def tool(name: str, hint: str) -> str:
    """Full path of a command-line tool (handles .cmd wrappers on Windows), or exit with a hint."""
    path = shutil.which(name)
    if path is None:
        fail(f"'{name}' was not found. {hint} Then open a NEW terminal and try again.")
    return path


def port_in_use(port: int) -> bool:
    """Whether something listens on localhost:port (IPv4 or IPv6, whichever localhost resolves to)."""
    try:
        with socket.create_connection(("localhost", port), timeout=0.5):
            return True
    except OSError:
        return False


def start(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.Popen:
    """Start a process in its own process group, so that stop() can end it and its children."""
    kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if IS_WINDOWS else {"start_new_session": True}
    return subprocess.Popen(cmd, cwd=cwd, env=env, **kwargs)  # noqa: S603 (fixed commands, no shell)


def stop(proc: subprocess.Popen) -> None:
    """Stop a process started by start() and everything it launched (even if it already exited)."""
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)  # noqa: S603, S607
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if not IS_WINDOWS:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def install(poetry: str, npm: str) -> None:
    print("==> Installing Python dependencies (apps/api)...")
    subprocess.run([poetry, "install"], cwd=API_DIR, check=True)  # noqa: S603
    print("==> Installing Node dependencies (apps/web)...")
    subprocess.run([npm, "ci"], cwd=WEB_DIR, check=True)  # noqa: S603


def dev_database_url(gcloud: str, args, processes: list[subprocess.Popen]) -> str:
    """Open the IAP tunnel to the dev database and return its SQLAlchemy URL."""
    print("==> Reading the dev database password from Secret Manager...")
    secret = subprocess.run(  # noqa: S603
        [
            gcloud,
            "secrets",
            "versions",
            "access",
            "latest",
            f"--secret={DEV_DB_SECRET}",
            f"--project={args.project}",
        ],
        capture_output=True,
        text=True,
    )
    if secret.returncode != 0:
        fail(
            "could not read the database password. Log in to Google Cloud first with\n"
            "    gcloud auth login\n"
            f"using the Google account that has access to the project '{args.project}'.\n\n"
            f"gcloud said: {secret.stderr.strip()}"
        )

    print(f"==> Opening the tunnel to the database (localhost:{args.tunnel_port})...")
    tunnel = start(
        [
            gcloud,
            "compute",
            "start-iap-tunnel",
            args.db_vm,
            "5432",
            f"--local-host-port=localhost:{args.tunnel_port}",
            f"--zone={args.zone}",
            f"--project={args.project}",
        ],
        cwd=ROOT,
    )
    processes.append(tunnel)
    deadline = time.monotonic() + TUNNEL_TIMEOUT_S
    while not port_in_use(args.tunnel_port):
        if tunnel.poll() is not None:
            fail("the database tunnel stopped (see the gcloud message above). Try `gcloud auth login`.")
        if time.monotonic() > deadline:
            fail(f"the database tunnel did not open within {TUNNEL_TIMEOUT_S} s.")
        time.sleep(0.5)

    password = quote(secret.stdout.strip(), safe="")
    return f"postgresql+psycopg://{DEV_DB}:{password}@localhost:{args.tunnel_port}/{DEV_DB}"


def interrupt(signum, frame):
    """Treat SIGTERM / SIGHUP (e.g. the terminal window is closed) like Ctrl+C."""
    raise KeyboardInterrupt


def main(argv=None):
    args = parse_args(argv)
    if not IS_WINDOWS:
        signal.signal(signal.SIGTERM, interrupt)
        signal.signal(signal.SIGHUP, interrupt)
    poetry = tool("poetry", "Install Poetry (see the README, 'One-time setup').")
    npm = tool("npm", "Install Node.js 20 LTS (see the README, 'One-time setup').")
    gcloud = (
        tool("gcloud", "Install the Google Cloud CLI (see the README, 'One-time setup').") if args.db == "dev" else ""
    )

    ports = [API_PORT, WEB_PORT] + ([args.tunnel_port] if args.db == "dev" else [])
    busy = [p for p in ports if port_in_use(p)]
    if busy:
        fail(f"port(s) {busy} already in use: is the site already running in another terminal? Stop it with Ctrl+C.")

    if args.install:
        install(poetry, npm)
    elif not (WEB_DIR / "node_modules").is_dir():
        fail("dependencies are not installed yet: run this script once with --install.")

    processes: list[subprocess.Popen] = []
    try:
        if args.db == "dev":
            database_url = dev_database_url(gcloud, args, processes)
        else:
            if not port_in_use(5432):
                fail("no local database on port 5432: start it with `make db-up migrate dev-seed` (needs Docker).")
            database_url = LOCAL_DATABASE_URL

        env = {**os.environ, "DATABASE_URL": database_url, "COOKIE_SECURE": "false", "ENV": "local"}
        print("==> Starting the API (http://localhost:8000/api/docs)...")
        processes.append(
            start([poetry, "run", "uvicorn", "seeing_api.main:app", "--reload", "--port", str(API_PORT)], API_DIR, env)
        )
        print("==> Starting the website...")
        processes.append(start([npm, "run", "dev"], WEB_DIR))

        print(f"\n    Open http://localhost:{WEB_PORT} in your browser. Press Ctrl+C here to stop.\n")
        while all(p.poll() is None for p in processes):
            time.sleep(1)
        print("\nOne of the programs stopped (see the messages above); stopping the others.")
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        for proc in reversed(processes):
            stop(proc)


if __name__ == "__main__":
    main()
