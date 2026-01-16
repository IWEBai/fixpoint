import json
from pathlib import Path

RESULTS_PATH = Path("semgrep_results.json")

def main():
    if not RESULTS_PATH.exists():
        print("semgrep_results.json not found.")
        return

    raw = RESULTS_PATH.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            text = raw.decode(enc)
            data = json.loads(text)
            break
        except Exception:
            data = None
    
    if data is None:
        raise RuntimeError("Could not decode semgrep_results.json as JSON. Re-generate the file.")
    
    results = data.get("results", [])

    if not results:
        print("No findings.")
        return

    print(f"Findings: {len(results)}\n")

    for r in results:
        check_id = r.get("check_id")
        path = r.get("path")
        start = r.get("start", {})
        end = r.get("end", {})
        extra = r.get("extra", {})
        message = extra.get("message", "").strip()

        print(f"- check_id: {check_id}")
        print(f"  file:     {path}")
        print(f"  start:    {start.get('line')}:{start.get('col')}")
        print(f"  end:      {end.get('line')}:{end.get('col')}")
        print(f"  message:  {message}")
        print()

if __name__ == "__main__":
    main()
