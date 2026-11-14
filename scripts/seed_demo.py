"""Seed a synthetic demo patient through the public API (M17). Synthetic data only.

    python scripts/seed_demo.py --base-url http://localhost:8080 [--email demo.patient@example.com]

Registers (or logs in), grants consent, uploads the synthetic reports for "Asha (Synthetic)",
waits for the worker to process them, then generates and approves a summary snapshot. The
password is read from DEMO_PASSWORD or generated and printed once; nothing is written to disk.
"""

import argparse
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.generate_synthetic_pdfs import _reports, generate  # noqa: E402

CSRF = {"X-CSRF-Protection": "1"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--base-url", default=os.environ.get("FRONTEND_ORIGIN", "http://127.0.0.1:8080")
    )
    parser.add_argument("--email", default="demo.patient@example.com")
    parser.add_argument("--timeout", type=float, default=180, help="seconds to wait for processing")
    args = parser.parse_args()
    password = os.environ.get("DEMO_PASSWORD") or secrets.token_urlsafe(12)
    api = f"{args.base_url.rstrip('/')}/api/v1"
    origin = {"Origin": args.base_url.rstrip("/")}

    with httpx.Client(timeout=30, headers=origin) as http:
        credentials = {"email": args.email, "password": password}
        registered = http.post(f"{api}/auth/register", json=credentials, headers=CSRF)
        if registered.status_code == 409 and not os.environ.get("DEMO_PASSWORD"):
            sys.exit("Account exists: set DEMO_PASSWORD to its password to re-seed it.")
        login = http.post(f"{api}/auth/login", json=credentials, headers=CSRF)
        login.raise_for_status()
        # The session cookie is Secure; send it explicitly so the script also works over plain
        # http on localhost (httpx, like browsers elsewhere, withholds Secure cookies on http).
        http.headers["Cookie"] = f"rk_access={login.cookies['rk_access']}"

        notice = http.get(f"{api}/patient/consent").json()
        http.post(
            f"{api}/patient/consent",
            json={"notice_version": notice["notice_version"]},
            headers=CSRF,
        ).raise_for_status()

        ids = []
        with tempfile.TemporaryDirectory() as tmp:
            generate(Path(tmp))
            for report in _reports():
                if report.patient.key != "asha":
                    continue
                pdf = (Path(tmp) / report.filename).read_bytes()
                response = http.post(
                    f"{api}/patient/documents",
                    files={"file": (report.filename, pdf, "application/pdf")},
                    headers=CSRF,
                )
                response.raise_for_status()
                ids.append(response.json()["id"])

        deadline = time.monotonic() + args.timeout
        while True:
            statuses = [http.get(f"{api}/patient/documents/{i}").json()["status"] for i in ids]
            if all(s in {"ready", "failed"} for s in statuses):
                break
            if time.monotonic() > deadline:
                sys.exit("Timed out waiting for the worker; is it running?")
            time.sleep(1)

        snapshot = http.post(f"{api}/patient/snapshots", headers=CSRF).json()
        http.post(
            f"{api}/patient/snapshots/{snapshot['id']}/approve", headers=CSRF
        ).raise_for_status()
        ready = statuses.count("ready")
        processed = f"{ready}/{len(ids)} documents processed"
        summary = f"summary v{snapshot['version']} approved"
        print(f"Demo patient ready: {args.email} ({processed}, {summary})")
        if not os.environ.get("DEMO_PASSWORD"):
            print(f"Password (shown once): {password}")


if __name__ == "__main__":
    main()
