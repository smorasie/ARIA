# ARIA

AI Research & Investment Assistant.

ARIA is a local AI-assisted trading project designed to help with
trade planning, position sizing, risk management, journaling and
trade analysis.

The project is being developed incrementally, starting with a small
core and expanding its capabilities over time.

## Current Status

Phase 0 — Foundation

Current sprint:

- Sprint 0.1 — Repository & Local Development Setup

The initial version of ARIA focuses on establishing the project
foundation. Trading functionality will be developed in later phases.

## Initial Core

The initial ARIA core will focus on:

- Trade planning
- Position-size calculations
- Risk calculations
- Trade journaling
- User-provided analysis and comments
- AI-assisted interpretation and analysis

Calculations such as position sizing and risk will be performed by
deterministic Python code rather than by the AI model.

## Repository Structure

```text
aria/
├── data/
│   ├── dummy/
│   └── README.md
├── docs/
├── src/
│   └── aria/
├── tests/
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md