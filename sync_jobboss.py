"""Pull employees / jobs / labor from JobBoss into Postgres.

Run this on a machine that can reach the JobBoss SQL Server, with the connection
configured via environment variables (see utils/jobboss.py for setup):

    pip install -r requirements-jobboss.txt
    export JOBBOSS_SERVER='192.168.1.50\\SQLEXPRESS'
    export JOBBOSS_DB='JOBBOSS_DB'
    export JOBBOSS_USER='readonly_user'
    export JOBBOSS_PASSWORD='...'
    .venv/bin/python sync_jobboss.py

Idempotent: re-running updates existing rows instead of duplicating them. If
JobBoss is unavailable it makes no changes and explains why (exit code 1).
"""
import sys

from utils.db import get_engine
from utils import jobboss


def main():
    print("Syncing from JobBoss into Postgres...")
    print(f"  {jobboss.status_text()}")
    result = jobboss.sync_to_postgres(get_engine())
    if not result["ok"]:
        print(f"  Skipped — {result['reason']}")
        return 1
    print(f"  Employees upserted: {result['employees']}")
    print(f"  Jobs upserted:      {result['jobs']}")
    print(f"  Labor upserted:     {result['labor']}")
    print("  Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
