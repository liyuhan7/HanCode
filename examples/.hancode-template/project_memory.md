# Project Memory

## Project Structure

HanCode uses a lightweight local `.hancode/` workspace to track course-project context,
task artifacts, trace events, and checkpoints.

## Technical Stack

- Python 3.11+
- pytest
- ruff
- mypy
- pydantic
- typer
- keyring
- Docker

## Run And Test Commands

- Test: `python -m pytest`
- Lint: `python -m ruff check src tests`
- Type check: `python -m mypy src`

## Constraints

- Do not write real credentials.
- Do not modify business code before SPEC and PLAN exist.
- Keep course assignment files, teacher tests, grading scripts, and sample data protected.
