# Repository Guide

## Keep In Git

Commit:

- `README.md`
- `AGENTS.md`
- `docs/event-format.md`
- `data/events/*.json`
- `data/templates/calendar.template.html`
- `scripts/*.py`
- `Makefile`

Do not commit generated output or local cache files. Those belong in `.gitignore`.

## Ignore In Git

Ignore:

- `dist/`
- `__pycache__/`
- `*.pyc`
- tool caches such as `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`

## Event Format

Use the format described in `docs/event-format.md`.

Rules:

- Create exactly one JSON file per real-world event under `data/events/`.
- Use a stable slug ID such as `acl-2026`.
- Keep all milestones for that event inside its own `dates` object.
- Use `related` references by `event_id` instead of copying dates from another event.
- If no date is known yet, leave `dates` empty and keep the uncertainty in `notes`. The site generator will place that record in the `TBA` section.

## Validation

After creating or editing an event file, validate it before finishing:

```bash
python3 scripts/validate_event_json.py data/events/<event-id>.json
```

To validate the full dataset:

```bash
python3 scripts/validate_event_json.py
```

The validator script is the repo contract. Do not add or rename fields casually; update the validator and the generator together if the model changes.
