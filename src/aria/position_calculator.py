import json
import math
import re
from datetime import datetime
from pathlib import Path


def forex_entry(
    account: dict,
    entry=0,
    stop=0,
    target=0,
    quote_per_account=1.0,
    pip_size=0.01,
    whole_units=True,
    leverage=1,
    instrument="GBPJPY",
    base_currency="GBP",
    quote_currency="JPY",
):
    if account.get("account_size"):
        account_size = account.get("account_size")
    else:
        raise ValueError("Please provide your account size.")
    if account.get("risk"):
        risk = account.get("risk")
    else:
        raise ValueError("Please provide your risk percentage.")
    if account.getget("leverage", 1):
        leverage = account.get("leverage")
    else:
        raise ValueError("Please provide your leverage.")
    if entry <= 0 or stop <= 0 or target <= 0:
        raise ValueError("Entry, stop and target must be positive.")
    if quote_per_account <= 0:
        raise ValueError(
            "quote_per_account must be positive; Use the current exhange rate for your default currency."
        )
    if pip_size <= 0:
        raise ValueError("pip_size must be positive.")
    if leverage <= 0:
        raise ValueError("leverage must be positive. Minimum 1 for no leverage.")

    if entry > stop:
        direction = "long"
        reward_per_unit_quote = target - entry
    elif entry < stop:
        direction = "short"
        reward_per_unit_quote = entry - target
    else:
        raise ValueError("Stop cannot equal entry.")

    risk_per_unit_quote = abs(entry - stop)

    if reward_per_unit_quote <= 0:
        raise ValueError("Target must be on the profitable side of entry.")

    max_risk = account_size * risk
    max_risk_quote = max_risk * quote_per_account
    risk_based_position_size = max_risk_quote / risk_per_unit_quote

    if whole_units:
        risk_based_position_size = int(risk_based_position_size)

    max_position = account_size * leverage
    max_position_base_currency = max_position

    if whole_units:
        max_position_base_currency = int(max_position_base_currency)

    position_size = min(risk_based_position_size, max_position_base_currency)

    actual_risk_quote = risk_per_unit_quote * position_size
    potential_reward_quote = reward_per_unit_quote * position_size
    actual_risk = actual_risk_quote / quote_per_account
    potential_reward = potential_reward_quote / quote_per_account
    rr = potential_reward / actual_risk
    position_limited_by_account = position_size < risk_based_position_size

    lines = []
    block = (
        f" ┌──────────────────────────────────────────────────────────────────\n"
        f"### [{instrument}] {base_currency} / {quote_currency}\n"
        f"### [ACCOUNT CURRENCY] {account.get('account_currency')}\n"
        f"### [ACCOUNT SIZE] {account_size} | [ACCOUNT RISK] {risk * 100}%\n\n"
        f"### [TRADE CALCULATIONS]:\n"
        f" |    Direction           : {direction}\n"
        f" |    Entry | Stop | TP   : {entry} | {stop} | {target}\n"
        f" |    Stop | target       : {round(risk_per_unit_quote / pip_size, 2)} | {round(reward_per_unit_quote / pip_size, 2)} pips\n"
        f" |    Position size       : {position_size} {base_currency}\n"
        f" |    Planned risk        : {round(actual_risk, 2):.2f} {base_currency}\n"
        f" |    Risk | Reward       : {round(rr, 2):.2f}R\n"
    )
    lines.append(block)
    return "\n\n".join(lines)


def futures_entry(
    account: dict,
    entry,
    stop,
    target,
    contract_multiplier,
    tick_size,
    quote_currency,
    quote_to_account_rate,
    initial_margin_quote,
    commission_round_turn_quote=0,
    slippage_ticks=0,
    max_margin_fraction=0.5,
    instrument="CUSTOM",
    instrument_name="Custom futures instrument",
    exchange="Custom",
):
    """Calculate whole-contract futures sizing from caller-supplied specs."""
    account_size = account.get("account_size")
    risk = account.get("risk")
    if account_size is None or account_size <= 0:
        raise ValueError("Please provide a positive account size.")
    if risk is None or risk <= 0:
        raise ValueError("Please provide a positive risk fraction.")

    commission = commission_round_turn_quote

    if any(value is None or value <= 0 for value in (entry, stop, target)):
        raise ValueError("Entry, stop and target must be positive.")
    if quote_to_account_rate is None or quote_to_account_rate <= 0:
        raise ValueError("quote_to_account_rate must be positive.")
    if initial_margin_quote is None or initial_margin_quote <= 0:
        raise ValueError("initial_margin_quote must be positive.")
    if commission < 0 or slippage_ticks < 0:
        raise ValueError("Commission and slippage cannot be negative.")
    if not 0 < max_margin_fraction <= 1:
        raise ValueError("max_margin_fraction must be greater than 0 and at most 1.")

    key = str(instrument).upper() if instrument else "CUSTOM"
    if contract_multiplier is None or contract_multiplier <= 0:
        raise ValueError("contract_multiplier must be positive.")
    if tick_size is None or tick_size <= 0:
        raise ValueError("tick_size must be positive.")
    if not quote_currency:
        raise ValueError("quote_currency is required.")

    if entry > stop:
        direction, reward_distance = "long", target - entry
    elif entry < stop:
        direction, reward_distance = "short", entry - target
    else:
        raise ValueError("Stop cannot equal entry.")
    if reward_distance <= 0:
        raise ValueError("Target must be on the profitable side of entry.")

    stop_distance = abs(entry - stop)
    stop_ticks = stop_distance / tick_size
    reward_ticks = reward_distance / tick_size
    for label, price in (("entry", entry), ("stop", stop), ("target", target)):
        if not math.isclose(price / tick_size, round(price / tick_size), rel_tol=0, abs_tol=1e-9):
            raise ValueError(f"{label} must lie on the contract tick grid.")
    if not math.isclose(stop_ticks, round(stop_ticks), rel_tol=0, abs_tol=1e-9):
        raise ValueError("Entry and stop distance must be an exact number of ticks.")
    if not math.isclose(reward_ticks, round(reward_ticks), rel_tol=0, abs_tol=1e-9):
        raise ValueError("Entry and target distance must be an exact number of ticks.")
    stop_ticks, reward_ticks = round(stop_ticks), round(reward_ticks)

    tick_value_quote = contract_multiplier * tick_size
    max_risk = account_size * risk
    risk_per_contract_quote = (stop_ticks + slippage_ticks) * tick_value_quote + commission
    risk_per_contract_account = risk_per_contract_quote * quote_to_account_rate
    reward_per_contract_account = (reward_ticks * tick_value_quote - commission) * quote_to_account_rate
    if reward_per_contract_account <= 0:
        raise ValueError("Target does not cover the configured round-turn costs.")

    by_risk = math.floor(max_risk / risk_per_contract_account)
    margin_budget = account_size * max_margin_fraction
    by_margin = math.floor(margin_budget / initial_margin_quote)
    contracts = min(by_risk, by_margin)
    warning = None
    if by_risk < 1:
        warning = "One contract exceeds the configured risk limit."
    elif by_margin < 1:
        warning = "One contract exceeds the configured margin budget."

    data = {
        "instrument": key,
        "instrument_name": instrument_name,
        "exchange": exchange,
        "quote_currency": quote_currency,
        "account_currency": account.get("account_currency"),
        "account_size": account_size,
        "risk_percent": risk * 100,
        "max_risk": round(max_risk, 2),
        "entry": entry,
        "stop": stop,
        "target": target,
        "direction": direction,
        "contract_multiplier": contract_multiplier,
        "tick_size": tick_size,
        "tick_value_quote": tick_value_quote,
        "quote_to_account_rate": quote_to_account_rate,
        "stop_distance_points": stop_distance,
        "stop_ticks": stop_ticks,
        "reward_distance_points": reward_distance,
        "reward_ticks": reward_ticks,
        "slippage_ticks": slippage_ticks,
        "commission_round_turn_quote": commission,
        "risk_per_contract_quote": round(risk_per_contract_quote, 6),
        "risk_per_contract_account": round(risk_per_contract_account, 2),
        "potential_reward_per_contract_quote": round(reward_ticks * tick_value_quote - commission, 6),
        "potential_reward_per_contract_account": round(reward_per_contract_account, 2),
        "risk_based_max_contracts": by_risk,
        "initial_margin_quote": initial_margin_quote,
        "margin_per_contract_account": round(initial_margin_quote, 2),
        "max_margin_fraction": max_margin_fraction,
        "margin_budget": round(margin_budget, 2),
        "margin_based_max_contracts": by_margin,
        "contracts": contracts,
        "can_trade_one_contract": contracts >= 1,
        "planned_risk": round(contracts * risk_per_contract_account, 2),
        "planned_margin": round(contracts * initial_margin_quote, 2),
        "risk_reward_ratio": round(reward_per_contract_account / risk_per_contract_account, 2),
        "warning": warning,
    }
    summary = (
        f"### [{key}] {instrument_name}\n"
        f"### [ACCOUNT CURRENCY] {account.get('account_currency')}\n"
        f"### [ACCOUNT SIZE] {account_size:,.2f} | [ACCOUNT RISK] {risk * 100:g}%\n\n"
        f"### [TRADE CALCULATIONS]\n"
        f" | Direction: {direction}\n"
        f" | Entry | Stop | TP: {entry} | {stop} | {target}\n"
        f" | Stop | Target: {stop_ticks} | {reward_ticks} ticks\n"
        f" | Position size: {contracts} contract(s)\n"
        f" | Planned risk: {data['planned_risk']:.2f}\n"
        f" | Planned margin: {data['planned_margin']:.2f}\n"
        f" | Risk | Reward: {data['risk_reward_ratio']:.2f}R\n"
        f" | Warning: {warning or 'None'}"
    )
    return data, summary


def position_calculator(account: dict, instrument: dict, trade: dict):
    if instrument.get("type") == "forex":
        return forex_entry(
            account,
            entry=trade.get("entry"),
            stop=trade.get("stop"),
            target=trade.get("target"),
            quote_per_account=instrument.get("quote"),
            pip_size=instrument.get("pip_size"),
            whole_units=instrument.get("whole", True),
        )
    if instrument.get("type") == "futures":
        return futures_entry(
            account,
            entry=trade.get("entry"),
            stop=trade.get("stop"),
            target=trade.get("target"),
            contract_multiplier=instrument.get("contract_multiplier"),
            tick_size=instrument.get("tick_size"),
            quote_currency=instrument.get("quote_currency"),
            quote_to_account_rate=instrument.get("quote_to_account_rate"),
            initial_margin_quote=instrument.get("initial_margin_quote"),
            commission_round_turn_quote=instrument.get("commission_round_turn_quote", 0),
            slippage_ticks=instrument.get("slippage_ticks", 0),
            max_margin_fraction=instrument.get("max_margin_fraction", 0.5),
            instrument=instrument.get("symbol", "CUSTOM"),
            instrument_name=instrument.get("instrument_name", "Custom futures instrument"),
            exchange=instrument.get("exchange", "Custom"),
        )
    raise ValueError("instrument type must be 'forex' or 'futures'.")


if __name__ == "__main__":
    account = {"account_size": 5000, "risk": 0.01, "account_currency": "GBP"}
    print(
        forex_entry(
            account,
            entry=209.520,
            stop=209.300,
            target=209.590,
            quote_per_account=209.45,  # exchange rate
            pip_size=0.01,
            whole_units=True,
            leverage=1,
        )
    )
