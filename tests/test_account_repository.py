import sqlite3

import pytest

from aria import account_repository as accounts
from aria.local import database


@pytest.fixture
def personal_database(tmp_path, monkeypatch):
    db_path = tmp_path / "account-tests.sqlite3"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    database.initialize_database("personal")
    return db_path


def _create_account(**overrides):
    values = {
        "account_size": 25_000,
        "risk_fraction": 0.01,
        "leverage": 10,
        "account_currency": "USD",
    }
    values.update(overrides)
    return accounts.create_account(**values)


def _insert_profile(conn, *, account_size=1_000):
    conn.execute(
        """INSERT INTO account_profiles (
               account_size, risk_fraction, leverage, account_currency,
               created_at, updated_at, last_confirmed_at
           ) VALUES (?, 0.01, 1, 'GBP', 'created', 'updated', 'confirmed')""",
        (account_size,),
    )


def test_create_retrieve_update_confirm_and_delete_account(personal_database):
    assert accounts.retrieve_active_account() is None

    created = _create_account(account_currency=" usd ")
    assert created["account_currency"] == "USD"
    assert accounts.retrieve_active_account() == created
    assert accounts.validate_account() == created

    confirmed = accounts.confirm_account()
    assert confirmed["last_confirmed_at"] >= created["last_confirmed_at"]
    assert confirmed["updated_at"] == created["updated_at"]

    updated = accounts.update_account(account_size=30_000, account_currency="gbp")
    assert updated["account_size"] == 30_000
    assert updated["account_currency"] == "GBP"
    assert updated["risk_fraction"] == created["risk_fraction"]
    assert updated["leverage"] == created["leverage"]
    assert updated["last_confirmed_at"] == confirmed["last_confirmed_at"]
    assert accounts.update_account() == updated

    assert accounts.delete_account(updated["id"]) is True
    assert accounts.delete_account(updated["id"]) is False
    assert accounts.retrieve_active_account() is None


@pytest.mark.parametrize(
    "field", ["account_size", "risk_fraction", "leverage", "account_currency"]
)
def test_create_account_rejects_none_for_required_fields(personal_database, field):
    with pytest.raises(ValueError, match=field):
        _create_account(**{field: None})


@pytest.mark.parametrize(
    "field", ["account_size", "risk_fraction", "leverage", "account_currency"]
)
def test_create_account_rejects_omitted_required_fields(personal_database, field):
    values = {
        "account_size": 25_000,
        "risk_fraction": 0.01,
        "leverage": 10,
        "account_currency": "USD",
    }
    del values[field]

    with pytest.raises(TypeError):
        accounts.create_account(**values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("account_size", 0),
        ("account_size", float("inf")),
        ("risk_fraction", 0),
        ("risk_fraction", 1.01),
        ("risk_fraction", float("nan")),
        ("leverage", 0),
        ("leverage", float("inf")),
        ("account_currency", "USÉ"),
    ],
)
def test_create_account_rejects_invalid_values(personal_database, field, value):
    with pytest.raises(ValueError):
        _create_account(**{field: value})


def test_create_account_rejects_a_second_profile(personal_database):
    first = _create_account()

    with pytest.raises(accounts.AccountAlreadyExistsError):
        _create_account(account_currency="GBP")

    assert accounts.retrieve_active_account() == first


def test_operations_report_missing_account(personal_database):
    with pytest.raises(accounts.AccountNotFoundError):
        accounts.update_account(account_size=1_000)
    with pytest.raises(accounts.AccountNotFoundError):
        accounts.confirm_account()
    with pytest.raises(accounts.AccountNotFoundError):
        accounts.validate_account()


def test_operations_report_ambiguous_profiles(personal_database):
    with database.get_conn() as conn:
        _insert_profile(conn, account_size=1_000)
        _insert_profile(conn, account_size=2_000)

    with pytest.raises(RuntimeError, match="Multiple account profiles"):
        accounts.retrieve_active_account()
    with pytest.raises(RuntimeError, match="Multiple account profiles"):
        accounts.update_account(account_size=3_000)
    with pytest.raises(RuntimeError, match="Multiple account profiles"):
        accounts.confirm_account()
    with pytest.raises(RuntimeError, match="Multiple account profiles"):
        accounts.validate_account()


def test_failed_update_rolls_back_without_changing_profile(personal_database):
    original = _create_account()
    with database.get_conn() as conn:
        conn.execute(
            """CREATE TRIGGER reject_account_update
               BEFORE UPDATE ON account_profiles
               BEGIN
                   SELECT RAISE(ABORT, 'update rejected');
               END"""
        )

    with pytest.raises(sqlite3.IntegrityError, match="update rejected"):
        accounts.update_account(account_size=50_000)

    assert accounts.retrieve_active_account() == original
