"""Generate now.html with embedded data. Called by daily.py _stamp_index."""
import json, sys, os

ROOT = os.path.dirname(os.path.abspath(__file__))

def generate():
    tracker_path = os.path.join(ROOT, "reports", "tracker.json")
    template_path = os.path.join(ROOT, "now_template.html")

    with open(tracker_path) as f:
        data = json.load(f)

    # Read template and inject data
    with open(template_path) as f:
        html = f.read()

    # Replace markers
    html = html.replace("__VERSION__", (data.get("_version") or "?")[:16])
    html = html.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False))

    output_path = os.path.join(ROOT, "now.html")
    with open(output_path, "w") as f:
        f.write(html)

    print(f"Generated now.html: {len(html)} bytes, version: {(data.get('_version') or '?')[:16]}")

if __name__ == "__main__":
    generate()
