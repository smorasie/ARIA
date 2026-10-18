import sqlite3

import pytest

from aria.local import database


@pytest.fixture
def isolated_database(tmp_path, monkeypatch):
    db_path = tmp_path / "nested" / "aria.sqlite3"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    monkeypatch.setattr(database, "SCHEMA_SQL_PATH", database.PACKAGE_SQL_PATH / "schema.sql")
    monkeypatch.setattr(database, "DEMO_SQL_PATH", database.PACKAGE_SQL_PATH / "seed_demo.sql")
    monkeypatch.setattr(database, "MIGRATIONS_PATH", database.PACKAGE_SQL_PATH / "migrations")
    return db_path


def test_repeated_demo_initialization_seeds_once_and_preserves_edits(isolated_database):
    database.initialize_database("demo")

    with database.get_conn() as conn:
        assert conn.execute("SELECT count(*) FROM account_profiles").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM instruments").fetchone()[0] == 2
        conn.execute("UPDATE account_profiles SET account_size = 12345 WHERE id = 1")
        conn.execute("UPDATE instruments SET name = 'My USDJPY label' WHERE symbol = 'USDJPY'")

    database.initialize_database("demo")

    with database.get_conn() as conn:
        assert conn.execute("SELECT count(*) FROM account_profiles").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM instruments").fetchone()[0] == 2
        assert conn.execute("SELECT account_size FROM account_profiles").fetchone()[0] == 12345
        assert conn.execute("SELECT name FROM instruments WHERE symbol = 'USDJPY'").fetchone()[0] == "My USDJPY label"
        assert conn.execute("SELECT demo_seeded FROM application_config").fetchone()[0] == 1


def test_personal_mode_never_seeds_demo_and_cannot_be_switched(isolated_database):
    database.initialize_database("personal")

    with database.get_conn() as conn:
        assert conn.execute("SELECT count(*) FROM account_profiles").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM instruments").fetchone()[0] == 0
        assert conn.execute("SELECT mode FROM application_config").fetchone()[0] == "personal"

    with pytest.raises(database.DatabaseInitializationError, match="configured for personal"):
        database.initialize_database("demo")

    with database.get_conn() as conn:
        assert conn.execute("SELECT count(*) FROM instruments").fetchone()[0] == 0


def test_failed_demo_initialization_rolls_back_schema_and_seed(isolated_database, tmp_path, monkeypatch):
    bad_seed = tmp_path / "bad_seed.sql"
    bad_seed.write_text(
        "CREATE TABLE seed_probe (value TEXT);\n"
        "INSERT INTO seed_probe VALUES ('partial');\n"
        "INSERT INTO table_that_does_not_exist VALUES (1);\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(database, "DEMO_SQL_PATH", bad_seed)

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        database.initialize_database("demo")

    with sqlite3.connect(isolated_database) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        assert tables == []


def test_unversioned_existing_data_is_preserved_and_rejected(isolated_database):
    isolated_database.parent.mkdir(parents=True)
    with sqlite3.connect(isolated_database) as conn:
        conn.execute("CREATE TABLE legacy_data (value TEXT NOT NULL)")
        conn.execute("INSERT INTO legacy_data VALUES ('keep me')")

    with pytest.raises(database.DatabaseInitializationError, match="no schema version"):
        database.initialize_database("personal")

    with sqlite3.connect(isolated_database) as conn:
        assert conn.execute("SELECT value FROM legacy_data").fetchone()[0] == "keep me"
        assert conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
        ).fetchone()[0] == 0


def test_version_one_database_is_migrated(isolated_database):
    isolated_database.parent.mkdir(parents=True)
    with sqlite3.connect(isolated_database) as conn:
        conn.executescript(database.SCHEMA_SQL_PATH.read_text(encoding="utf-8"))

    database.initialize_database("personal")

    with database.get_conn() as conn:
        assert conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()[0] == 2
        assert conn.execute("SELECT mode FROM application_config").fetchone()[0] == "personal"


def test_failed_migration_rolls_back_and_preserves_existing_rows(
    isolated_database, tmp_path, monkeypatch
):
    database.initialize_database("personal")
    with database.get_conn() as conn:
        conn.execute(
            "INSERT INTO account_profiles "
            "(account_size, risk_fraction, leverage, account_currency, created_at, updated_at, last_confirmed_at) "
            "VALUES (1000, 0.01, 1, 'GBP', 'created', 'updated', 'confirmed')"
        )

    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0003_broken.sql").write_text(
        "ALTER TABLE account_profiles ADD COLUMN migration_probe TEXT;\n"
        "INSERT INTO missing_table VALUES (1);\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(database, "MIGRATIONS_PATH", migrations)

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        database.initialize_database("personal")

    with database.get_conn() as conn:
        assert conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()[0] == 2
        assert conn.execute("SELECT account_size FROM account_profiles").fetchone()[0] == 1000
        columns = {row[1] for row in conn.execute("PRAGMA table_info(account_profiles)")}
        assert "migration_probe" not in columns
