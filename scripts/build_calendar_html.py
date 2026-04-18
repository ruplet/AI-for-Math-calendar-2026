#!/usr/bin/env python3

import argparse
import html
import json
import re
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVENTS_DIR = ROOT / "data" / "events"
TEMPLATE_PATH = ROOT / "data" / "templates" / "calendar.template.html"
OUTPUT_PATH = ROOT / "dist" / "calendar.html"


def read_events():
    events = []
    for path in sorted(EVENTS_DIR.glob("*.json")):
        events.append(json.loads(path.read_text()))
    return events


def index_events(events):
    return {event["id"]: event for event in events if isinstance(event, dict) and isinstance(event.get("id"), str)}


def primary_anchor_key(event):
    dates = event.get("dates", {})
    if "event" in dates:
        return "event"
    return next(iter(dates), None)


def parse_anchor(value):
    kind = value.get("type")
    if kind == "date":
        return value.get("value"), False
    if kind == "date_range":
        return value.get("start"), False
    if kind == "date_choice":
        return None, True
    return None, True


def classify_rows(events, event_index, today_iso: str):
    today_value = date.fromisoformat(today_iso)
    upcoming = []
    past = []
    unsure = []
    for event in events:
        dates = event.get("dates", {})
        if not dates:
            unsure.append(build_unsure_row(event, event_index))
            continue
        anchor_key = primary_anchor_key(event)
        for milestone_key, milestone in dates.items():
            value = milestone["value"]
            anchor_iso, _ = parse_anchor(value)
            row = build_row(event, milestone_key, milestone, event_index, anchor_key)
            if anchor_iso:
                anchor_date = date.fromisoformat(anchor_iso)
                row["anchor_date"] = anchor_date
                if anchor_date >= today_value:
                    upcoming.append(row)
                else:
                    past.append(row)
            else:
                row["event_anchor_id"] = f"{event['id']}-{milestone_key}"
                unsure.append(row)
    upcoming.sort(key=lambda row: (row["anchor_date"], row["event_title"], row["milestone_label"]))
    past.sort(key=lambda row: (row["anchor_date"], row["event_title"], row["milestone_label"]), reverse=True)
    unsure.sort(key=lambda row: (row["event_title"], row["milestone_label"]))
    return upcoming, past, unsure


def build_row(event, milestone_key, milestone, event_index, anchor_key):
    return {
        "event_title": event["title"],
        "event_id": event["id"],
        "milestone_key": milestone_key,
        "milestone_label": milestone["label"],
        "location": event.get("location"),
        "notes_html": render_notes_html(event, event_index, anchor_key),
        "display_date": render_date_value(milestone["value"]),
        "event_anchor_id": event["id"] if milestone_key == anchor_key else "",
        "event_link_html": render_event_title(event, event["id"]),
    }


def build_unsure_row(event, event_index):
    return {
        "event_title": event["title"],
        "event_id": event["id"],
        "milestone_label": "unspecified",
        "location": event.get("location"),
        "notes_html": render_notes_html(event, event_index, None),
        "display_date": "Unsure",
        "event_anchor_id": event["id"],
        "event_link_html": render_event_title(event, event["id"]),
    }


def relation_label(relation_type):
    if relation_type == "parent_event":
        return "Parent conference"
    if relation_type == "colocated_with":
        return "Co-located with"
    if relation_type == "covers_event":
        return "Covers"
    return relation_type.replace("_", " ").capitalize()


def render_event_preview(event):
    items = []
    source_url = event.get("source_url")
    dates = event.get("dates", {})
    conference = dates.get("event")
    if conference:
        items.append(render_preview_item("conference", render_date_value(conference["value"]), "ref-popover-item-conference"))
    for milestone_key, milestone in sorted(
        ((key, value) for key, value in dates.items() if key != "event"),
        key=lambda item: preview_milestone_sort_key(item[1]["value"]),
    ):
        if milestone_key == "event":
            continue
        items.append(render_preview_item(milestone["label"], render_date_value(milestone["value"])))
    preview_lines = [
        render_event_preview_title(event["title"], source_url),
    ]
    if event.get("location"):
        preview_lines.append(f'<div class="ref-popover-sub">{html.escape(event["location"])}</div>')
    if items:
        preview_lines.append('<div class="ref-popover-sub">Deadlines</div>')
        preview_lines.append('<ul class="ref-popover-list">' + "".join(items) + "</ul>")
    return "".join(preview_lines)


def preview_milestone_sort_key(value):
    kind = value.get("type")
    if kind == "date":
        return (0, value.get("value") or "", "")
    if kind == "date_range":
        return (0, value.get("start") or "", value.get("end") or "")
    if kind == "date_choice":
        values = value.get("values") or []
        return (0, values[0] if values else "", "")
    text = value.get("raw") or value.get("value") or ""
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if match:
        return (0, match.group(0), text)
    return (1, text, "")


def normalize_preview_label(label):
    if not label:
        return label
    return label[:1].upper() + label[1:]


def render_preview_item(label, value, item_class=""):
    class_attr = f' class="{item_class}"' if item_class else ""
    return (
        f"<li{class_attr}>"
        f'<span class="ref-popover-label">{html.escape(normalize_preview_label(label))}</span>'
        f'<span class="ref-popover-value">{html.escape(value)}</span>'
        "</li>"
    )


def render_event_preview_title(title, source_url):
    safe_title = html.escape(title)
    if not source_url:
        return f'<div class="ref-popover-title">{safe_title}</div>'
    safe_source = html.escape(source_url)
    return (
        '<div class="ref-popover-title">'
        f'<a href="{safe_source}" target="_blank" rel="noopener noreferrer">{safe_title}</a>'
        "</div>"
    )


def render_event_link(target_event):
    preview = render_event_preview(target_event)
    return (
        '<span class="ref-link event-ref">'
        f'<a href="#{html.escape(target_event["id"])}">{html.escape(target_event["title"])}</a>'
        f'<span class="ref-popover">{preview}</span>'
        "</span>"
    )


def render_event_title(event, target_anchor_id):
    preview = render_event_preview(event)
    title_link = (
        '<span class="ref-link event-ref">'
        f'<a href="#{html.escape(target_anchor_id)}">{html.escape(event["title"])}</a>'
        f'<span class="ref-popover">{preview}</span>'
        "</span>"
    )
    return title_link


def render_notes_html(event, event_index, anchor_key):
    items = []
    for note in event.get("notes", []):
        items.append(f"<li>{html.escape(note)}</li>")
    for idx, long_note in enumerate(event.get("long_notes", []) or []):
        note_id = f"long-note-{event['id']}-{idx}"
        items.append(f'<li><a href="#{note_id}">Long note</a></li>')
    for relation in event.get("related", []):
        label = relation_label(relation.get("type", "related"))
        target = event_index.get(relation.get("event_id"))
        if target:
            items.append(
                "<li>"
                f"{html.escape(label)}: "
                f"{render_event_link(target)}"
                "</li>"
            )
        else:
            items.append(
                f"<li>{html.escape(label)}: {html.escape(relation.get('event_id', ''))}</li>"
            )
    if not items:
        return ""
    return '<ul class="notes">' + "".join(items) + "</ul>"


def render_date_value(value):
    kind = value.get("type")
    if kind == "date":
        return value["value"]
    if kind == "date_range":
        return f"{value['start']} to {value['end']}"
    if kind == "date_choice":
        return " or ".join(value.get("values", []))
    return value.get("raw", "")


def render_rows(rows):
    if not rows:
        return '<tr><td colspan="3" class="empty">No rows in this section.</td></tr>'
    rendered = []
    for row in rows:
        event_meta = []
        if row["location"]:
            event_meta.append(html.escape(row["location"]))
        event_meta_html = "<br>".join(event_meta)
        id_attr = f' id="{html.escape(row["event_anchor_id"])}"' if row["event_anchor_id"] else ""
        rendered.append(
            "\n".join(
                [
                    f"<tr{id_attr}>",
                    f'  <td><span class="date-main">{html.escape(row["display_date"])}</span></td>',
                    f'  <td class="event-cell"><div class="event-title">{row["event_link_html"]}</div><div class="event-meta">{event_meta_html}</div></td>',
                    f'  <td>{html.escape(row["milestone_label"])}</td>',
                    f"  <td>{row['notes_html']}</td>",
                    "</tr>",
                ]
            )
        )
    return "\n".join(rendered)


def render_unsure(rows):
    if not rows:
        return ""
    items = []
    for row in rows:
        id_attr = f' id="{html.escape(row["event_anchor_id"])}"' if row["event_anchor_id"] else ""
        items.append(
            "\n".join(
                [
                    f"<tr{id_attr}>",
                    f'  <td><span class="date-main">{html.escape(row["display_date"] or "Unsure")}</span></td>',
                    f'  <td class="event-cell"><div class="event-title">{row["event_link_html"]}</div><div class="event-meta">{html.escape(row["location"] or "")}</div></td>',
                    f'  <td>{html.escape(row["milestone_label"])}</td>',
                    f"  <td>{row['notes_html']}</td>",
                    "</tr>",
                ]
            )
        )
    return (
        '<div class="section-header"><h2>Unsure</h2></div>'
        '<div class="table-wrap"><table><thead><tr><th>Date</th><th>Event</th><th>Milestone</th><th>Notes</th></tr></thead><tbody>'
        + "".join(items)
        + "</tbody></table></div>"
    )


def render_long_notes(events):
    rows = []
    for event in events:
        long_notes = event.get("long_notes") or []
        if not long_notes:
            continue
        back_target = event["id"] if primary_anchor_key(event) else event["id"]
        for idx, text in enumerate(long_notes):
            note_id = f"long-note-{event['id']}-{idx}"
            rows.append(
                "\n".join(
                    [
                        f'<tr id="{note_id}">',
                        f'  <td>{html.escape(event["title"])}</td>',
                        f'  <td>{html.escape(text)} <a href="#{back_target}">Back to table</a></td>',
                        "</tr>",
                    ]
                )
            )
    if not rows:
        return ""
    return (
        '<section class="section"><h2>Long Notes</h2>'
        '<div class="table-wrap"><table><thead><tr><th>Event</th><th>Long note</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></div></section>"
    )


def render_page(events, today_iso: str):
    template = TEMPLATE_PATH.read_text()
    event_index = index_events(events)
    upcoming, past, unsure = classify_rows(events, event_index, today_iso)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    replacements = {
        "{{GENERATED_AT}}": generated_at,
        "{{TODAY_LABEL}}": today_iso,
        "{{EVENT_COUNT}}": str(len(events)),
        "{{ROW_COUNT}}": str(len(upcoming) + len(past) + len(unsure)),
        "{{UPCOMING_ROWS}}": render_rows(upcoming),
        "{{PAST_ROWS}}": render_rows(past),
        "{{UNSURE_BLOCK}}": render_unsure(unsure),
        "{{LONG_NOTES_BLOCK}}": render_long_notes(events),
    }
    html_text = template
    for needle, replacement in replacements.items():
        html_text = html_text.replace(needle, replacement)
    return html_text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--today", default=date.today().isoformat(), help="Reference date in YYYY-MM-DD")
    parser.add_argument("--output", default=str(OUTPUT_PATH), help="Output HTML path")
    args = parser.parse_args()

    events = read_events()
    zero_date_events = [event["id"] for event in events if not event.get("dates")]
    for event_id in zero_date_events:
        print(f"WARNING: event has no dated milestones and will be rendered in Unsure: {event_id}")
    html_text = render_page(events, args.today)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_text)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
