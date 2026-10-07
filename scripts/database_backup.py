"""Custom-format PostgreSQL backup/restore; secrets stay out of process arguments."""

import argparse
import os
import subprocess
from pathlib import Path

from sqlalchemy.engine import make_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("file", type=Path)
    parser.add_argument("--bin-dir", type=Path)
    args = parser.parse_args()
    raw_url = os.environ.get("BACKUP_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not raw_url:
        parser.error("Set BACKUP_DATABASE_URL or DATABASE_URL in the environment")
    url = make_url(raw_url)
    if url.get_backend_name() != "postgresql":
        parser.error("PostgreSQL is required")
    env = os.environ.copy()
    env.update(
        PGHOST=url.host or "localhost",
        PGPORT=str(url.port or 5432),
        PGUSER=url.username or "postgres",
        PGPASSWORD=url.password or "",
        PGDATABASE=url.database or "postgres",
        PGSSLMODE=url.query.get("sslmode", "require"),
        PGCONNECT_TIMEOUT="10",
    )
    binary = "pg_dump" if args.action == "backup" else "pg_restore"
    executable = (
        str(args.bin_dir / (binary + (".exe" if os.name == "nt" else "")))
        if args.bin_dir
        else binary
    )
    if args.action == "backup":
        if args.file.exists():
            parser.error("Refusing to overwrite an existing backup")
        args.file.parent.mkdir(parents=True, exist_ok=True)
        command = [
            executable,
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(args.file),
        ]
    else:
        if not args.file.is_file():
            parser.error("Backup file does not exist")
        # No --clean: the operator must provide a separate empty destination DB.
        command = [
            executable,
            "--exit-on-error",
            "--no-owner",
            "--no-privileges",
            "--dbname",
            url.database,
            str(args.file),
        ]
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    if result.returncode:
        # Provider errors can contain database URLs; avoid dumping raw stderr.
        raise SystemExit(
            f"{args.action} failed (exit {result.returncode}); check destination, privileges, and PostgreSQL tool version"
        )
    print(f"{args.action} completed: {args.file.name}")


if __name__ == "__main__":
    main()
