"""Persistence operations for the local account profile."""

import math
from datetime import datetime, timezone

from aria.local import database


class AccountAlreadyExistsError(RuntimeError):
    """Raised when creating a profile would replace an existing one."""


class AccountNotFoundError(LookupError):
    """Raised when an operation requires an account but none exists."""


def _validated_profile_fields(
    *,
    account_size: int | float | None = None,
    risk_fraction: int | float | None = None,
    leverage: int | float | None = None,
    account_currency: str | None = None,
) -> dict[str, int | float | str]:
    """Validate supplied profile values and return their normalized fields."""
    fields: dict[str, int | float | str] = {}

    if account_size is not None:
        if (
            isinstance(account_size, bool)
            or not isinstance(account_size, (int, float))
            or not math.isfinite(account_size)
            or account_size <= 0
        ):
            raise ValueError("account_size must be a finite number greater than zero.")
        fields["account_size"] = account_size

    if risk_fraction is not None:
        if (
            isinstance(risk_fraction, bool)
            or not isinstance(risk_fraction, (int, float))
            or not math.isfinite(risk_fraction)
            or not 0 < risk_fraction <= 1
        ):
            raise ValueError("risk_fraction must be greater than 0 and at most 1.")
        fields["risk_fraction"] = risk_fraction

    if leverage is not None:
        if (
            isinstance(leverage, bool)
            or not isinstance(leverage, (int, float))
            or not math.isfinite(leverage)
            or leverage < 1
        ):
            raise ValueError("leverage must be a finite number of at least 1.")
        fields["leverage"] = leverage

    if account_currency is not None:
        if not isinstance(account_currency, str):
            raise ValueError("account_currency must be a three-letter currency code.")
        normalized_currency = account_currency.strip().upper()
        if (
            len(normalized_currency) != 3
            or not normalized_currency.isascii()
            or not normalized_currency.isalpha()
        ):
            raise ValueError("account_currency must be a three-letter currency code.")
        fields["account_currency"] = normalized_currency

    return fields


def _utc_timestamp() -> str:
    """Return an ISO 8601 UTC timestamp with millisecond precision."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def retrieve_active_account() -> dict[str, object] | None:
    """Return the only configured account profile, or ``None`` if none exists.

    The current schema does not identify an active profile. Until it does, multiple
    profiles are ambiguous and must not be silently resolved to an arbitrary row.
    """
    with database.get_conn() as conn:
        rows = conn.execute(
            """SELECT id, account_size, risk_fraction, leverage, account_currency,
                      created_at, updated_at, last_confirmed_at
               FROM account_profiles
               ORDER BY id
               LIMIT 2"""
        ).fetchall()

    if len(rows) > 1:
        raise RuntimeError(
            "Multiple account profiles exist, but the database does not define "
            "which profile is active."
        )

    if not rows:
        return None

    return dict(rows[0])


def delete_account(account_id: int) -> bool:
    """Delete a profile by ID; return whether a matching profile was found."""
    if (
        isinstance(account_id, bool)
        or not isinstance(account_id, int)
        or account_id < 1
    ):
        raise ValueError("account_id must be a positive integer.")

    with database.get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM account_profiles WHERE id = ?", (account_id,)
        )
        return cursor.rowcount == 1


def create_account(
    account_size: int | float,
    risk_fraction: float,
    leverage: int | float,
    account_currency: str,
) -> dict[str, object]:
    """Create and return the installation's single account profile.

    Values are checked before writing, and an immediate transaction prevents two
    concurrent calls from both passing the single-profile check.
    """
    required_fields = {
        "account_size": account_size,
        "risk_fraction": risk_fraction,
        "leverage": leverage,
        "account_currency": account_currency,
    }
    missing_fields = [name for name, value in required_fields.items() if value is None]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise ValueError(f"Required account field(s) missing: {missing}.")

    fields = _validated_profile_fields(
        account_size=account_size,
        risk_fraction=risk_fraction,
        leverage=leverage,
        account_currency=account_currency,
    )

    with database.get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT 1 FROM account_profiles LIMIT 1").fetchone()
        if existing is not None:
            raise AccountAlreadyExistsError(
                "An account profile already exists; delete it before creating another."
            )

        # New values are treated as confirmed at account creation.
        now = _utc_timestamp()
        cursor = conn.execute(
            """INSERT INTO account_profiles (
                   account_size, risk_fraction, leverage, account_currency,
                   created_at, updated_at, last_confirmed_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                fields["account_size"],
                fields["risk_fraction"],
                fields["leverage"],
                fields["account_currency"],
                now,
                now,
                now,
            ),
        )
        row = conn.execute(
            """SELECT id, account_size, risk_fraction, leverage, account_currency,
                      created_at, updated_at, last_confirmed_at
               FROM account_profiles WHERE id = ?""",
            (cursor.lastrowid,),
        ).fetchone()

    return dict(row)


def update_account(
    account_size: int | float | None = None,
    risk_fraction: int | float | None = None,
    leverage: int | float | None = None,
    account_currency: str | None = None,
) -> dict[str, object]:
    """Update supplied fields on the single account profile and return it.

    Omitted values (``None``) remain unchanged. Updating profile data advances
    ``updated_at`` but leaves ``last_confirmed_at`` as the last explicit confirmation.
    """
    fields = _validated_profile_fields(
        account_size=account_size,
        risk_fraction=risk_fraction,
        leverage=leverage,
        account_currency=account_currency,
    )

    with database.get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            """SELECT id, account_size, risk_fraction, leverage, account_currency,
                      created_at, updated_at, last_confirmed_at
               FROM account_profiles ORDER BY id LIMIT 2"""
        ).fetchall()
        if not rows:
            raise AccountNotFoundError("No account profile exists to update.")
        if len(rows) > 1:
            raise RuntimeError(
                "Multiple account profiles exist, but the database does not define "
                "which profile is active."
            )

        account_id = rows[0]["id"]
        if fields:
            # Column names come only from the fixed, validated field mapping above;
            # values remain SQL parameters.
            assignments = ", ".join(f"{name} = ?" for name in fields)
            values = [*fields.values(), _utc_timestamp(), account_id]
            conn.execute(
                f"UPDATE account_profiles SET {assignments}, updated_at = ? WHERE id = ?",
                values,
            )

        row = conn.execute(
            """SELECT id, account_size, risk_fraction, leverage, account_currency,
                      created_at, updated_at, last_confirmed_at
               FROM account_profiles WHERE id = ?""",
            (account_id,),
        ).fetchone()

    return dict(row)


def confirm_account() -> dict[str, object]:
    """Record that the user has confirmed the existing account values.

    This updates ``last_confirmed_at`` only. Whether confirmation is due (for
    example, after seven days) is a separate policy decision for the caller.
    """
    with database.get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT id FROM account_profiles ORDER BY id LIMIT 2"
        ).fetchall()
        if len(rows) > 1:
            raise RuntimeError(
                "Multiple account profiles exist, but the database does not define "
                "which profile is active."
            )
        if not rows:
            raise AccountNotFoundError("No account profile exists to confirm.")

        account_id = rows[0]["id"]
        confirmed_at = _utc_timestamp()
        conn.execute(
            "UPDATE account_profiles SET last_confirmed_at = ? WHERE id = ?",
            (confirmed_at, account_id),
        )
        row = conn.execute(
            """SELECT id, account_size, risk_fraction, leverage, account_currency,
                      created_at, updated_at, last_confirmed_at
               FROM account_profiles WHERE id = ?""",
            (account_id,),
        ).fetchone()

    return dict(row)


def validate_account() -> dict[str, object]:
    """Validate and return the saved account profile without changing it.

    The database schema also enforces these constraints. This check provides a
    repository-level validation step for callers before they use the profile.
    """
    account = retrieve_active_account()
    if account is None:
        raise AccountNotFoundError("No account profile exists to validate.")

    _validated_profile_fields(
        account_size=account["account_size"],
        risk_fraction=account["risk_fraction"],
        leverage=account["leverage"],
        account_currency=account["account_currency"],
    )
    return account
