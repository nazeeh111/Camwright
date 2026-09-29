"""Isolated calculation entry point, invoked only by the local server."""
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    # The server uses an absolute bundled script with Python's isolated mode.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from camwright.engine import calculate, refused
from camwright.project import MAX_BODY, parse_json


def main():
    try:
        raw = sys.stdin.buffer.read(MAX_BODY+1)
        request = parse_json(raw)
        result = calculate(request["operation"], request["project"], request.get("project_id"))
    except (ValueError, KeyError, TypeError, MemoryError) as error:
        result = refused("calculation_error", str(error))
    sys.stdout.write(json.dumps(result, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
