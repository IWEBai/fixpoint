from __future__ import annotations

from pathlib import Path
import re


# Very narrow MVP: only fix "query = f'...{email}...'" followed by "cursor.execute(query)"
RE_QUERY = re.compile(r'^(?P<indent>\s*)query\s*=\s*f(?P<quote>["\'])(?P<sql>.*)\2\s*$', re.M)
RE_EXEC = re.compile(r'^(?P<indent>\s*)cursor\.execute\(\s*query\s*\)\s*$', re.M)


def apply_fix_sqli(repo_path: Path, target_relpath: str = "app.py") -> bool:
    """
    Apply deterministic SQLi fix to repo_path/target_relpath.
    Returns True if a patch was applied, otherwise False (pattern mismatch).
    """
    repo_path = Path(repo_path)
    target_file = repo_path / target_relpath

    if not target_file.exists():
        print(f"ABORT: Target file not found: {target_file}")
        return False

    text = target_file.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines(True)

    # Find query line
    q_idx = None
    q_match = None
    for i, line in enumerate(lines):
        m = RE_QUERY.match(line.rstrip("\n"))
        if m:
            q_idx = i
            q_match = m
            break

    if q_idx is None or q_match is None:
        print("ABORT: Did not find expected f-string query assignment pattern.")
        return False

    # Find execute(query) after it
    exec_idx = None
    for j in range(q_idx + 1, min(q_idx + 15, len(lines))):
        if RE_EXEC.match(lines[j].rstrip("\n")):
            exec_idx = j
            break

    if exec_idx is None:
        print("ABORT: Did not find 'cursor.execute(query)' near the query assignment.")
        return False

    indent = q_match.group("indent")
    quote = q_match.group("quote")
    sql = q_match.group("sql")

    # MVP assumption: exactly one interpolated variable: {email}
    if "{email}" not in sql:
        print("ABORT: Expected '{email}' interpolation inside the SQL string.")
        return False

    # Convert f-string SQL to parameterized SQL
    # Replace '{email}' first to remove quoting, then remaining {email}
    param_sql = sql.replace("'{email}'", "%s").replace("{email}", "%s")

    new_query_line = f"{indent}query = {quote}{param_sql}{quote}\n"
    new_exec_line = f"{indent}cursor.execute(query, (email,))\n"

    old_query_line = lines[q_idx]
    old_exec_line = lines[exec_idx]

    # If already patched, do nothing
    if old_query_line.strip() == new_query_line.strip() and old_exec_line.strip() == new_exec_line.strip():
        print("No changes needed (already patched).")
        return False

    # Apply patch
    lines[q_idx] = new_query_line
    lines[exec_idx] = new_exec_line

    target_file.write_text("".join(lines), encoding="utf-8")

    print("PATCH APPLIED:")
    print(f"- {target_file}")
    print(f"  Replaced: {old_query_line.strip()}  -->  {new_query_line.strip()}")
    print(f"  Replaced: {old_exec_line.strip()}  -->  {new_exec_line.strip()}")

    return True


def main():
    # Local manual test mode
    demo_repo = Path(r"E:\autopatcher-demo-python")
    apply_fix_sqli(demo_repo)


if __name__ == "__main__":
    main()
