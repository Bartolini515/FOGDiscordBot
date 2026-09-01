"""Run committed SQLite migrations as an explicit offline deployment step."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from db.database import apply_committed_migrations, pending_migration_ids


def parse_arguments() -> argparse.Namespace:
    """Parse the explicitly selected database and migration inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path, help="SQLite database file to inspect or migrate")
    parser.add_argument("--migrations", type=Path, help="Directory containing committed yoyo migrations")
    parser.add_argument("--check", action="store_true", help="Report pending migrations without changing the database")
    return parser.parse_args()


def main() -> int:
    """Check or apply migrations for the database selected by the operator."""
    arguments = parse_arguments()
    try:
        if arguments.check:
            pending = pending_migration_ids(arguments.database, arguments.migrations)
            if pending:
                print(f"Pending migrations: {', '.join(pending)}")
                return 1
            print("No pending migrations.")
            return 0

        applied = apply_committed_migrations(arguments.database, arguments.migrations)
        pending = pending_migration_ids(arguments.database, arguments.migrations)
    except Exception:
        print("Migration failed: unable to inspect or apply the selected database.", file=sys.stderr)
        return 1

    if pending:
        print(f"Pending migrations: {', '.join(pending)}")
        return 1
    if applied:
        print(f"Applied migrations: {', '.join(applied)}")
    else:
        print("No pending migrations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
