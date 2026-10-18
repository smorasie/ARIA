"""SQLite initialization and migration helpers for ARIA's local database."""

import os
import re
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path


def _default_data_directory() -> Path:
    """Return a per-user application data directory on the current platform."""
    if sys.platform == "win32":
        return (
            Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            / "ARIA"
        )
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ARIA"
    return (
        Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "aria"
    )


DB_PATH = _default_data_directory() / "aria.db"
PACKAGE_SQL_PATH = Path(__file__).resolve().parents[1] / "sql"
SCHEMA_SQL_PATH = PACKAGE_SQL_PATH / "schema.sql"
DEMO_SQL_PATH = PACKAGE_SQL_PATH / "seed_demo.sql"
MIGRATIONS_PATH = PACKAGE_SQL_PATH / "migrations"
BASE_SCHEMA_VERSION = 1


class DatabaseInitializationError(RuntimeError):
    """Raised when an existing database cannot be safely initialized."""


@contextmanager
def get_conn():
    """Yield a database connection and commit or roll back its transaction."""
    database_path = Path(DB_PATH).expanduser()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _execute_sql_script(conn: sqlite3.Connection, script: str) -> None:
    """Execute complete SQL statements without executescript's implicit commits."""
    pending = ""
    for line in script.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            statement = pending.strip()
            if statement:
                conn.execute(statement)
            pending = ""

    tail = pending.strip()
    if tail and any(
        line.strip() and not line.lstrip().startswith("--")
        for line in tail.splitlines()
    ):
        raise DatabaseInitializationError(
            "SQL script ends with an incomplete statement."
        )


def _user_tables(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _schema_version(conn: sqlite3.Connection) -> int:
    tables = _user_tables(conn)
    if "schema_version" not in tables:
        if tables:
            raise DatabaseInitializationError(
                "Existing database has tables but no schema version; refusing to modify it."
            )
        return 0

    rows = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchall()
    if len(rows) != 1:
        raise DatabaseInitializationError(
            "Database must contain exactly one schema version row."
        )
    return int(rows[0][0])


def _migration_files() -> dict[int, Path]:
    migrations: dict[int, Path] = {}
    for path in Path(MIGRATIONS_PATH).glob("*.sql"):
        match = re.fullmatch(r"(\d{4})_[A-Za-z0-9_-]+\.sql", path.name)
        if not match:
            continue
        version = int(match.group(1))
        if version in migrations:
            raise DatabaseInitializationError(
                f"Duplicate migration version: {version}."
            )
        migrations[version] = path
    return migrations


def _apply_migrations(conn: sqlite3.Connection, version: int) -> int:
    migrations = _migration_files()
    latest = max([BASE_SCHEMA_VERSION, *migrations], default=BASE_SCHEMA_VERSION)
    if version > latest:
        raise DatabaseInitializationError(
            "Database schema is newer than the available migrations."
        )

    while version < latest:
        next_version = version + 1
        migration_path = migrations.get(next_version)
        if migration_path is None:
            raise DatabaseInitializationError(
                f"Missing migration for schema version {next_version}."
            )
        _execute_sql_script(conn, migration_path.read_text(encoding="utf-8"))
        conn.execute(
            "UPDATE schema_version SET version = ?, applied_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now') WHERE id = 1",
            (next_version,),
        )
        version = next_version
    return version


def _initialize_schema(conn: sqlite3.Connection) -> int:
    version = _schema_version(conn)
    if version == 0:
        _execute_sql_script(conn, Path(SCHEMA_SQL_PATH).read_text(encoding="utf-8"))
        version = _schema_version(conn)
        if version != BASE_SCHEMA_VERSION:
            raise DatabaseInitializationError(
                f"Base schema must declare version {BASE_SCHEMA_VERSION}, got {version}."
            )
    elif version < BASE_SCHEMA_VERSION:
        raise DatabaseInitializationError(f"Unsupported schema version {version}.")

    version = _apply_migrations(conn, version)
    required_tables = {"schema_version", "account_profiles", "instruments"}
    missing_tables = required_tables - _user_tables(conn)
    if missing_tables:
        missing = ", ".join(sorted(missing_tables))
        raise DatabaseInitializationError(f"Database is missing required table(s): {missing}.")
    return version


def _row_count(conn: sqlite3.Connection, table: str) -> int:
    if table not in _user_tables(conn):
        return 0
    return int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])


def initialize_database(mode: str) -> None:
    """Initialize or migrate the database, explicitly binding it to one mode.

    Demo fixtures are applied once, transactionally, and only to a database whose
    configured mode is ``demo``. A database cannot be silently switched between
    demo and personal modes.
    """
    if mode not in {"demo", "personal"}:
        raise ValueError("mode must be 'demo' or 'personal'.")

    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        tables_before = _user_tables(conn)
        version = _initialize_schema(conn)

        if version < 2:
            raise DatabaseInitializationError(
                "Application mode migration was not applied."
            )

        config = conn.execute(
            "SELECT mode, demo_seeded FROM application_config WHERE id = 1"
        ).fetchone()
        if config is None:
            # Do not guess whether unlabelled records are personal or demo data.
            if tables_before and (
                _row_count(conn, "account_profiles") or _row_count(conn, "instruments")
            ):
                raise DatabaseInitializationError(
                    "Existing account or instrument data has no saved mode; refusing to classify it."
                )
            conn.execute(
                "INSERT INTO application_config (id, mode, demo_seeded) VALUES (1, ?, 0)",
                (mode,),
            )
            demo_seeded = 0
        else:
            if config["mode"] != mode:
                raise DatabaseInitializationError(
                    f"Database is configured for {config['mode']} mode, not {mode} mode."
                )
            demo_seeded = int(config["demo_seeded"])

        if mode == "demo" and not demo_seeded:
            demo_sql = Path(DEMO_SQL_PATH).read_text(encoding="utf-8")
            _execute_sql_script(conn, demo_sql)
            conn.execute("UPDATE application_config SET demo_seeded = 1 WHERE id = 1")
