# Contributing to Fixpoint

Thank you for your interest in contributing to Fixpoint by IWEB.

---

## How to Contribute

### Report bugs or ask questions

- **Bug or security issue:** [Open an Issue](https://github.com/IWEBai/fixpoint/issues) or see [SECURITY.md](SECURITY.md) for sensitive reports.
- **Feature idea or question:** [Start a Discussion](https://github.com/IWEBai/fixpoint/discussions).

### Code contributions

1. **Fork** the repository and clone your fork.
2. **Create a branch** from `main`: `git checkout -b fix/your-change` or `feature/your-feature`.
3. **Make your changes.** Keep the scope small and focused.
4. **Run tests:** `pip install -r requirements.txt && pip install semgrep && pytest`
5. **Commit** with a clear message, e.g. `fix: ...` or `feat: ...`.
6. **Push** to your fork and open a **Pull Request** against `main`.

We'll review your PR and may ask for small edits. Once approved, we'll merge it.

### Documentation

Improvements to README, docs, or comments are welcome. Open a PR with your edits.

---

## Development setup

```bash
git clone https://github.com/IWEBai/fixpoint.git
cd fixpoint
pip install -r requirements.txt
pip install semgrep   # for full test run (Linux/macOS)
pytest
```

### Golden snapshot workflow

Golden fixtures live under [tests/golden](tests/golden). If a fixer output changes,
tests will fail until you intentionally update snapshots:

```bash
FIXPOINT_UPDATE_GOLDENS=1 pytest tests/test_golden.py
```

Optional regression gate (no new Semgrep findings for the same rule family):

```bash
FIXPOINT_SEMGREP_GATE=1 pytest tests/test_golden.py
```

---

## Questions?

- **Website:** [iwebai.space](https://www.iwebai.space)
- **Community:** [r/IWEBai on Reddit](https://www.reddit.com/r/IWEBai/)
- **Discussions:** [GitHub Discussions](https://github.com/IWEBai/fixpoint/discussions)

---

_Fixpoint by [IWEB](https://www.iwebai.space)_
