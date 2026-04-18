PYTHON ?= python3
TODAY ?= $(shell date +%F)

.PHONY: all validate calendar clean

all: calendar

validate:
	$(PYTHON) scripts/validate_event_json.py

calendar: validate
	$(PYTHON) scripts/build_calendar_html.py --today $(TODAY) --output dist/calendar.html

clean:
	rm -rf dist
