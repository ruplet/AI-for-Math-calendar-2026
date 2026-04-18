#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVENTS_DIR = ROOT / "data" / "events"
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_KEY_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VALID_KINDS = {
    "event",
    "support_program",
    "conference",
    "workshop",
    "seminar",
    "school",
    "job",
    "grant",
    "program",
    "other",
}


def fail(path: Path, message: str) -> str:
    return f"{path}: {message}"


def validate_date_value(path: Path, value, prefix: str) -> list[str]:
    errors = []
    if not isinstance(value, dict):
        return [fail(path, f"{prefix} must be an object")]
    kind = value.get("type")
    raw = value.get("raw")
    if kind not in {"date", "date_range", "date_choice", "approximate", "text"}:
        errors.append(fail(path, f"{prefix}.type is invalid"))
        return errors
    if not isinstance(raw, str):
        errors.append(fail(path, f"{prefix}.raw must be a string"))
    allowed_keys = {
        "date": {"type", "value", "raw"},
        "date_range": {"type", "start", "end", "raw"},
        "date_choice": {"type", "values", "raw"},
        "approximate": {"type", "value", "raw"},
        "text": {"type", "value", "raw"},
    }[kind]
    extra_keys = sorted(set(value) - allowed_keys)
    for key in extra_keys:
        errors.append(fail(path, f"{prefix} has unexpected field '{key}'"))
    if kind in {"date", "approximate", "text"}:
        date_value = value.get("value")
        if not isinstance(date_value, str) or not date_value:
            errors.append(fail(path, f"{prefix}.value must be a non-empty string"))
    if kind == "date" and isinstance(value.get("value"), str) and not DATE_RE.match(value["value"]):
        errors.append(fail(path, f"{prefix}.value must be YYYY-MM-DD for type 'date'"))
    if kind == "date_range":
        for field in ("start", "end"):
            date_value = value.get(field)
            if not isinstance(date_value, str) or not DATE_RE.match(date_value):
                errors.append(fail(path, f"{prefix}.{field} must be YYYY-MM-DD"))
    if kind == "date_choice":
        choices = value.get("values")
        if not isinstance(choices, list) or not choices:
            errors.append(fail(path, f"{prefix}.values must be a non-empty array"))
        else:
            for idx, choice in enumerate(choices):
                if not isinstance(choice, str) or not DATE_RE.match(choice):
                    errors.append(fail(path, f"{prefix}.values[{idx}] must be YYYY-MM-DD"))
    return errors


def validate_date_field(path: Path, key: str, field) -> list[str]:
    errors = []
    if not isinstance(field, dict):
        return [fail(path, f"dates.{key} must be an object")]
    extra_keys = sorted(set(field) - {"label", "value"})
    for extra_key in extra_keys:
        errors.append(fail(path, f"dates.{key} has unexpected field '{extra_key}'"))
    label = field.get("label")
    if not isinstance(label, str) or not label:
        errors.append(fail(path, f"dates.{key}.label must be a non-empty string"))
    errors.extend(validate_date_value(path, field.get("value"), f"dates.{key}.value"))
    return errors


def validate_related(path: Path, related, valid_event_ids: set[str]) -> list[str]:
    errors = []
    if not isinstance(related, list):
        return [fail(path, "related must be an array")]
    for idx, item in enumerate(related):
        if not isinstance(item, dict):
            errors.append(fail(path, f"related[{idx}] must be an object"))
            continue
        extra_keys = sorted(set(item) - {"type", "event_id"})
        for extra_key in extra_keys:
            errors.append(fail(path, f"related[{idx}] has unexpected field '{extra_key}'"))
        relation_type = item.get("type")
        if not isinstance(relation_type, str) or not relation_type:
            errors.append(fail(path, f"related[{idx}].type must be a non-empty string"))
        event_id = item.get("event_id")
        if not isinstance(event_id, str) or not ID_RE.match(event_id):
            errors.append(fail(path, f"related[{idx}].event_id has invalid format"))
        elif event_id not in valid_event_ids:
            errors.append(fail(path, f"related[{idx}].event_id does not reference an existing event"))
    return errors


def validate_event_file(path: Path, valid_kinds: set[str], valid_event_ids: set[str]) -> list[str]:
    errors = []
    try:
        event = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return [fail(path, f"invalid JSON: {exc}")]

    required = {"id", "title", "kind", "dates", "related"}
    if not isinstance(event, dict):
        return [fail(path, "root must be an object")]

    extra_keys = sorted(set(event) - {
        "id", "title", "kind", "series", "year", "location", "source_url", "notes", "long_notes", "dates", "related"
    })
    missing_keys = sorted(required - set(event))
    for key in missing_keys:
        errors.append(fail(path, f"missing required field '{key}'"))
    for key in extra_keys:
        errors.append(fail(path, f"unexpected field '{key}'"))

    event_id = event.get("id")
    if not isinstance(event_id, str) or not ID_RE.match(event_id):
        errors.append(fail(path, "id must match ^[a-z0-9]+(?:-[a-z0-9]+)*$"))
    title = event.get("title")
    if not isinstance(title, str) or not title:
        errors.append(fail(path, "title must be a non-empty string"))
    if event.get("kind") not in valid_kinds:
        errors.append(fail(path, f"kind must be one of: {', '.join(sorted(valid_kinds))}"))

    source_url = event.get("source_url")
    if source_url is not None and (not isinstance(source_url, str) or not re.match(r"^https?://", source_url)):
        errors.append(fail(path, "source_url must be a non-empty http(s) URL string"))

    series = event.get("series")
    if series is not None and (not isinstance(series, str) or not series):
        errors.append(fail(path, "series must be a non-empty string or null"))

    year = event.get("year")
    if year is not None and (not isinstance(year, int) or year < 1900 or year > 3000):
        errors.append(fail(path, "year must be null or an integer between 1900 and 3000"))

    location = event.get("location")
    if location is not None and not isinstance(location, str):
        errors.append(fail(path, "location must be a string or null"))

    notes = event.get("notes", [])
    if not isinstance(notes, list) or any(not isinstance(item, str) for item in notes):
        errors.append(fail(path, "notes must be an array of strings"))

    long_notes = event.get("long_notes")
    if long_notes is not None and (
        not isinstance(long_notes, list) or any(not isinstance(item, str) for item in long_notes)
    ):
        errors.append(fail(path, "long_notes must be an array of strings or null"))

    dates = event.get("dates")
    if not isinstance(dates, dict):
        errors.append(fail(path, "dates must be an object"))
    else:
        for key, value in dates.items():
            if not DATE_KEY_RE.match(key):
                errors.append(fail(path, f"dates key '{key}' has invalid format"))
            errors.extend(validate_date_field(path, key, value))

    errors.extend(validate_related(path, event.get("related"), valid_event_ids))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", help="Event files to validate. Defaults to all data/events/*.json")
    args = parser.parse_args()

    paths = [Path(path) for path in args.paths] if args.paths else sorted(EVENTS_DIR.glob("*.json"))
    valid_event_ids = set()
    for event_path in sorted(EVENTS_DIR.glob("*.json")):
        try:
            event = json.loads(event_path.read_text())
        except json.JSONDecodeError:
            continue
        event_id = event.get("id")
        if isinstance(event_id, str):
            valid_event_ids.add(event_id)
    all_errors = []
    for path in paths:
        all_errors.extend(validate_event_file(path, VALID_KINDS, valid_event_ids))

    if all_errors:
        for error in all_errors:
            print(error, file=sys.stderr)
        print(f"Validation failed for {len(paths)} file(s)", file=sys.stderr)
        return 1

    print(f"Validated {len(paths)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
