"""
Configuration loader for Fixpoint.
Loads repo-specific settings from .fixpoint.yml / .fixpoint.yaml.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from yaml.nodes import MappingNode, SequenceNode


class ConfigError(Exception):
    """Raised when .fixpoint.yml fails schema validation."""

    def __init__(self, path: Path, errors: list[str]) -> None:
        self.path = path
        self.errors = errors
        super().__init__("; ".join(errors))


# Default configuration values
DEFAULT_MAX_DIFF_LINES = 500
DEFAULT_TEST_BEFORE_COMMIT = False
DEFAULT_TEST_COMMAND = "pytest"

# Additional safety defaults
DEFAULT_MAX_FILES_CHANGED = 10
DEFAULT_SENSITIVE_PATHS_ALLOWLIST: list[str] = []
DEFAULT_ALLOW_DEPENDENCY_CHANGES = False
DEFAULT_MAX_RUNTIME_SECONDS = 90

# Rule / policy defaults
DEFAULT_RULES_ENABLED: list[str] = []
DEFAULT_RULES_ENFORCE_PER_RULE: dict[str, str] = {}
DEFAULT_RULES_SEVERITY_THRESHOLD = "ERROR"

# Baseline + directory policies
DEFAULT_BASELINE_MODE = False
DEFAULT_BASELINE_SHA: str | None = None
DEFAULT_BASELINE_MAX_AGE_DAYS: int = 0
DEFAULT_DIRECTORY_POLICIES: dict[str, dict] = {}

# Formatting defaults
DEFAULT_FORMAT_AFTER_PATCH = True
DEFAULT_MAX_FORMAT_EXPANSION = 0.2

# Preset rule keys used by config init
PRESET_RULE_KEYS: list[str] = [
    "sqli",
    "secrets",
    "xss",
    "command-injection",
    "path-traversal",
    "ssrf",
    "eval",
    "dom-xss",
]

# Preset configurations (used by `fixpoint config init`)
PRESET_CONFIGS: dict[str, dict[str, Any]] = {
    "starter": {
        "max_diff_lines": 200,
        "test_before_commit": False,
        "test_command": "pytest",
        "max_files_changed": 5,
        "sensitive_paths_allowlist": [],
        "allow_dependency_changes": False,
        "max_runtime_seconds": 60,
        "rules": {
            "enabled": list(PRESET_RULE_KEYS),
            "enforce_per_rule": {key: "warn" for key in PRESET_RULE_KEYS},
            "severity_threshold": "ERROR",
        },
        "baseline_mode": False,
        "baseline_sha": None,
        "baseline_max_age_days": 0,
        "directory_policies": {},
        "format_after_patch": True,
        "max_format_expansion": 0.2,
    },
    "balanced": {
        "max_diff_lines": 400,
        "test_before_commit": False,
        "test_command": "pytest",
        "max_files_changed": 8,
        "sensitive_paths_allowlist": [],
        "allow_dependency_changes": False,
        "max_runtime_seconds": 90,
        "rules": {
            "enabled": list(PRESET_RULE_KEYS),
            "enforce_per_rule": {
                "sqli": "enforce",
                "secrets": "enforce",
                "dom-xss": "enforce",
                "xss": "warn",
                "command-injection": "warn",
                "path-traversal": "warn",
                "ssrf": "warn",
                "eval": "warn",
            },
            "severity_threshold": "ERROR",
        },
        "baseline_mode": False,
        "baseline_sha": None,
        "baseline_max_age_days": 0,
        "directory_policies": {},
        "format_after_patch": True,
        "max_format_expansion": 0.2,
    },
    "strict": {
        "max_diff_lines": 300,
        "test_before_commit": True,
        "test_command": "pytest",
        "max_files_changed": 6,
        "sensitive_paths_allowlist": [],
        "allow_dependency_changes": False,
        "max_runtime_seconds": 60,
        "rules": {
            "enabled": list(PRESET_RULE_KEYS),
            "enforce_per_rule": {
                "sqli": "enforce",
                "secrets": "enforce",
                "dom-xss": "enforce",
                "xss": "enforce",
                "command-injection": "enforce",
                "path-traversal": "enforce",
                "ssrf": "warn",
                "eval": "warn",
            },
            "severity_threshold": "WARNING",
        },
        "baseline_mode": False,
        "baseline_sha": None,
        "baseline_max_age_days": 0,
        "directory_policies": {},
        "format_after_patch": True,
        "max_format_expansion": 0.1,
    },
    "tailored": {
        "max_diff_lines": 400,
        "test_before_commit": False,
        "test_command": "pytest",
        "max_files_changed": 8,
        "sensitive_paths_allowlist": [],
        "allow_dependency_changes": False,
        "max_runtime_seconds": 90,
        "rules": {
            "enabled": list(PRESET_RULE_KEYS),
            "enforce_per_rule": {
                "sqli": "enforce",
                "secrets": "enforce",
                "xss": "enforce",
                "command-injection": "enforce",
                "path-traversal": "enforce",
                "ssrf": "enforce",
                "eval": "enforce",
                "dom-xss": "enforce",
            },
            "severity_threshold": "ERROR",
        },
        "baseline_mode": False,
        "baseline_sha": None,
        "baseline_max_age_days": 0,
        "directory_policies": {
            "src/security/": {
                "severity_threshold": "WARNING",
                "enforce_per_rule": {
                    "sqli": "enforce",
                    "secrets": "enforce",
                    "xss": "enforce",
                    "command-injection": "enforce",
                    "path-traversal": "enforce",
                    "ssrf": "enforce",
                    "eval": "enforce",
                    "dom-xss": "enforce",
                },
            },
            "src/auth/": {
                "severity_threshold": "WARNING",
                "enforce_per_rule": {
                    "sqli": "enforce",
                    "secrets": "enforce",
                    "xss": "enforce",
                    "command-injection": "enforce",
                    "path-traversal": "enforce",
                    "ssrf": "enforce",
                    "eval": "enforce",
                    "dom-xss": "enforce",
                },
            },
            "tests/": {
                "severity_threshold": "ERROR",
                "enforce_per_rule": {
                    "sqli": "warn",
                    "secrets": "warn",
                    "xss": "warn",
                    "command-injection": "warn",
                    "path-traversal": "warn",
                    "ssrf": "warn",
                    "eval": "warn",
                    "dom-xss": "warn",
                },
            },
            "scripts/": {
                "severity_threshold": "ERROR",
                "enforce_per_rule": {
                    "sqli": "warn",
                    "secrets": "warn",
                    "xss": "warn",
                    "command-injection": "warn",
                    "path-traversal": "warn",
                    "ssrf": "warn",
                    "eval": "warn",
                    "dom-xss": "warn",
                },
            },
        },
        "format_after_patch": True,
        "max_format_expansion": 0.2,
    },
}


def get_preset_names() -> list[str]:
    return sorted(PRESET_CONFIGS.keys())


def get_preset_config(preset: str) -> dict[str, Any]:
    key = str(preset or "").strip().lower()
    if key not in PRESET_CONFIGS:
        raise ValueError(f"Unknown preset: {preset}")
    # Return a shallow copy to avoid mutation
    return dict(PRESET_CONFIGS[key])


def render_preset_yaml(preset: str) -> str:
    key = str(preset or "").strip().lower()
    if key not in PRESET_CONFIGS:
        raise ValueError(f"Unknown preset: {preset}")
    header = (
        "# Fixpoint config preset: " + key + "\n"
        "# Generated by `fixpoint config init`\n"
        "# Docs: https://github.com/IWEBai/fixpoint\n\n"
    )
    data = PRESET_CONFIGS[key]
    body = yaml.safe_dump(data, sort_keys=False)
    return header + body


_ALLOWED_TOP_LEVEL_KEYS = {
    "max_diff_lines",
    "test_before_commit",
    "test_command",
    "max_files_changed",
    "sensitive_paths_allowlist",
    "allow_dependency_changes",
    "max_runtime_seconds",
    "rules",
    "baseline_mode",
    "baseline_sha",
    "baseline_max_age_days",
    "directory_policies",
    "format_after_patch",
    "max_format_expansion",
}
_ALLOWED_RULE_KEYS = {"enabled", "enforce_per_rule", "severity_threshold"}
_ALLOWED_DIR_POLICY_KEYS = {"severity_threshold", "enforce_per_rule"}
_VALID_SEVERITY = {"INFO", "WARNING", "WARN", "ERROR"}
_VALID_RULE_MODES = {"warn", "enforce"}


def _collect_line_map(node, prefix: str, line_map: dict[str, int]) -> None:
    if isinstance(node, MappingNode):
        for key_node, value_node in node.value:
            key = str(key_node.value)
            path = f"{prefix}.{key}" if prefix else key
            line_map[path] = int(key_node.start_mark.line) + 1
            _collect_line_map(value_node, path, line_map)
    elif isinstance(node, SequenceNode):
        for idx, item in enumerate(node.value):
            path = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            line_map[path] = int(item.start_mark.line) + 1
            _collect_line_map(item, path, line_map)


def _get_line(line_map: dict[str, int], path: str) -> str:
    line = line_map.get(path)
    return f"line {line}" if line else "line ?"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _add_error(errors: list[str], line_map: dict[str, int], path: str, message: str) -> None:
    errors.append(f"{_get_line(line_map, path)} ({path}): {message}")


def _validate_config_data(data: Any, line_map: dict[str, int]) -> list[str]:
    errors: list[str] = []
    if data is None:
        return errors
    if not isinstance(data, dict):
        errors.append("line ? (root): Config must be a mapping (key/value pairs).")
        return errors

    for key in data.keys():
        if key not in _ALLOWED_TOP_LEVEL_KEYS:
            _add_error(
                errors,
                line_map,
                str(key),
                "Unknown field. Allowed: " + ", ".join(sorted(_ALLOWED_TOP_LEVEL_KEYS)),
            )

    if "max_diff_lines" in data and not _is_number(data["max_diff_lines"]):
        _add_error(errors, line_map, "max_diff_lines", "Expected a positive number.")
    if "max_diff_lines" in data and _is_number(data["max_diff_lines"]) and data["max_diff_lines"] <= 0:
        _add_error(errors, line_map, "max_diff_lines", "Must be > 0.")

    if "test_before_commit" in data and not isinstance(data["test_before_commit"], bool):
        _add_error(errors, line_map, "test_before_commit", "Expected true/false.")
    if "test_command" in data and not isinstance(data["test_command"], str):
        _add_error(errors, line_map, "test_command", "Expected a string.")

    if "max_files_changed" in data and not _is_number(data["max_files_changed"]):
        _add_error(errors, line_map, "max_files_changed", "Expected a non-negative number.")
    if "max_files_changed" in data and _is_number(data["max_files_changed"]) and data["max_files_changed"] < 0:
        _add_error(errors, line_map, "max_files_changed", "Must be >= 0.")

    if "sensitive_paths_allowlist" in data and not isinstance(data["sensitive_paths_allowlist"], list):
        _add_error(errors, line_map, "sensitive_paths_allowlist", "Expected a list of strings.")
    if isinstance(data.get("sensitive_paths_allowlist"), list):
        for idx, item in enumerate(data["sensitive_paths_allowlist"]):
            if not isinstance(item, str):
                _add_error(errors, line_map, f"sensitive_paths_allowlist[{idx}]", "Expected a string.")

    if "allow_dependency_changes" in data and not isinstance(data["allow_dependency_changes"], bool):
        _add_error(errors, line_map, "allow_dependency_changes", "Expected true/false.")

    if "max_runtime_seconds" in data:
        val = data["max_runtime_seconds"]
        if val is not None and not _is_number(val):
            _add_error(errors, line_map, "max_runtime_seconds", "Expected a non-negative number or null.")
        if _is_number(val) and val < 0:
            _add_error(errors, line_map, "max_runtime_seconds", "Must be >= 0.")

    if "baseline_mode" in data and not isinstance(data["baseline_mode"], bool):
        _add_error(errors, line_map, "baseline_mode", "Expected true/false.")
    if "baseline_sha" in data and data["baseline_sha"] is not None and not isinstance(data["baseline_sha"], str):
        _add_error(errors, line_map, "baseline_sha", "Expected a string or null.")
    if "baseline_max_age_days" in data:
        val = data["baseline_max_age_days"]
        if not _is_number(val):
            _add_error(errors, line_map, "baseline_max_age_days", "Expected a non-negative number.")
        elif val < 0:
            _add_error(errors, line_map, "baseline_max_age_days", "Must be >= 0.")

    if "format_after_patch" in data and not isinstance(data["format_after_patch"], bool):
        _add_error(errors, line_map, "format_after_patch", "Expected true/false.")
    if "max_format_expansion" in data:
        val = data["max_format_expansion"]
        if not _is_number(val):
            _add_error(errors, line_map, "max_format_expansion", "Expected a non-negative number.")
        elif val < 0:
            _add_error(errors, line_map, "max_format_expansion", "Must be >= 0.")

    if "rules" in data:
        rules = data["rules"]
        if not isinstance(rules, dict):
            _add_error(errors, line_map, "rules", "Expected a mapping.")
        else:
            for key in rules.keys():
                if key not in _ALLOWED_RULE_KEYS:
                    _add_error(
                        errors,
                        line_map,
                        f"rules.{key}",
                        "Unknown field. Allowed: " + ", ".join(sorted(_ALLOWED_RULE_KEYS)),
                    )
            if "enabled" in rules and not isinstance(rules["enabled"], list):
                _add_error(errors, line_map, "rules.enabled", "Expected a list of strings.")
            if "enforce_per_rule" in rules and not isinstance(rules["enforce_per_rule"], dict):
                _add_error(errors, line_map, "rules.enforce_per_rule", "Expected a mapping of rule_key -> warn|enforce.")
            if "severity_threshold" in rules:
                val = str(rules["severity_threshold"]).upper()
                if val not in _VALID_SEVERITY:
                    _add_error(
                        errors,
                        line_map,
                        "rules.severity_threshold",
                        "Expected one of INFO, WARNING, WARN, ERROR.",
                    )
            if isinstance(rules.get("enabled"), list):
                for idx, item in enumerate(rules["enabled"]):
                    if not isinstance(item, str):
                        _add_error(errors, line_map, f"rules.enabled[{idx}]", "Expected a string.")
            if isinstance(rules.get("enforce_per_rule"), dict):
                for k, v in rules["enforce_per_rule"].items():
                    if not isinstance(k, str):
                        _add_error(errors, line_map, "rules.enforce_per_rule", "Rule keys must be strings.")
                    mode = str(v).lower()
                    if mode not in _VALID_RULE_MODES:
                        _add_error(
                            errors,
                            line_map,
                            "rules.enforce_per_rule",
                            "Rule values must be 'warn' or 'enforce'.",
                        )

    if "directory_policies" in data:
        policies = data["directory_policies"]
        if not isinstance(policies, dict):
            _add_error(errors, line_map, "directory_policies", "Expected a mapping of path -> policy.")
        else:
            for key, value in policies.items():
                path_key = f"directory_policies.{key}"
                if not isinstance(key, str):
                    _add_error(errors, line_map, "directory_policies", "Directory keys must be strings.")
                if not isinstance(value, dict):
                    _add_error(errors, line_map, path_key, "Expected a mapping for policy.")
                    continue
                for pkey in value.keys():
                    if pkey not in _ALLOWED_DIR_POLICY_KEYS:
                        _add_error(
                            errors,
                            line_map,
                            f"{path_key}.{pkey}",
                            "Unknown field. Allowed: " + ", ".join(sorted(_ALLOWED_DIR_POLICY_KEYS)),
                        )
                if "severity_threshold" in value:
                    val = str(value["severity_threshold"]).upper()
                    if val not in _VALID_SEVERITY:
                        _add_error(
                            errors,
                            line_map,
                            f"{path_key}.severity_threshold",
                            "Expected one of INFO, WARNING, WARN, ERROR.",
                        )
                if "enforce_per_rule" in value and not isinstance(value["enforce_per_rule"], dict):
                    _add_error(
                        errors,
                        line_map,
                        f"{path_key}.enforce_per_rule",
                        "Expected a mapping of rule_key -> warn|enforce.",
                    )

    return errors


def _load_yaml_with_lines(raw: str) -> tuple[dict[str, Any], dict[str, int]]:
    line_map: dict[str, int] = {}
    if not raw.strip():
        return {}, line_map
    node = yaml.compose(raw)
    if node is not None:
        _collect_line_map(node, "", line_map)
    data = yaml.safe_load(raw) or {}
    return data, line_map


def load_config(repo_path: Path) -> dict[str, Any]:
    """
    Load Fixpoint configuration from repo root.
    
    Searches for .fixpoint.yml or .fixpoint.yaml in repo_path.
    Environment variables override config file values:
    - FIXPOINT_MAX_DIFF_LINES
    - FIXPOINT_TEST_BEFORE_COMMIT
    - FIXPOINT_TEST_COMMAND
    
    Args:
        repo_path: Path to repository root
    
    Returns:
        Config dict with keys: max_diff_lines, test_before_commit, test_command
    """
    config: dict[str, Any] = {
        "max_diff_lines": DEFAULT_MAX_DIFF_LINES,
        "test_before_commit": DEFAULT_TEST_BEFORE_COMMIT,
        "test_command": DEFAULT_TEST_COMMAND,
        "max_files_changed": DEFAULT_MAX_FILES_CHANGED,
        "sensitive_paths_allowlist": list(DEFAULT_SENSITIVE_PATHS_ALLOWLIST),
        "allow_dependency_changes": DEFAULT_ALLOW_DEPENDENCY_CHANGES,
        "max_runtime_seconds": DEFAULT_MAX_RUNTIME_SECONDS,
        "rules": {
            "enabled": list(DEFAULT_RULES_ENABLED),
            "enforce_per_rule": dict(DEFAULT_RULES_ENFORCE_PER_RULE),
            "severity_threshold": DEFAULT_RULES_SEVERITY_THRESHOLD,
        },
        "baseline_mode": DEFAULT_BASELINE_MODE,
        "baseline_sha": DEFAULT_BASELINE_SHA,
        "baseline_max_age_days": DEFAULT_BASELINE_MAX_AGE_DAYS,
        "directory_policies": dict(DEFAULT_DIRECTORY_POLICIES),
        "format_after_patch": DEFAULT_FORMAT_AFTER_PATCH,
        "max_format_expansion": DEFAULT_MAX_FORMAT_EXPANSION,
    }
    
    for name in (".fixpoint.yml", ".fixpoint.yaml"):
        config_path = repo_path / name
        if config_path.exists():
            try:
                raw = config_path.read_text(encoding="utf-8", errors="replace")
                data, line_map = _load_yaml_with_lines(raw)
                errors = _validate_config_data(data, line_map)
                if errors:
                    raise ConfigError(config_path, errors)
                if isinstance(data, dict):
                    if "max_diff_lines" in data:
                        val = data["max_diff_lines"]
                        if isinstance(val, (int, float)) and val > 0:
                            config["max_diff_lines"] = int(val)
                    if "test_before_commit" in data:
                        config["test_before_commit"] = bool(data["test_before_commit"])
                    if "test_command" in data:
                        cmd = data["test_command"]
                        if isinstance(cmd, str) and cmd.strip():
                            config["test_command"] = cmd.strip()
                    if "max_files_changed" in data:
                        val = data["max_files_changed"]
                        if isinstance(val, (int, float)) and val > 0:
                            config["max_files_changed"] = int(val)
                    if "sensitive_paths_allowlist" in data:
                        paths = data["sensitive_paths_allowlist"]
                        if isinstance(paths, list):
                            config["sensitive_paths_allowlist"] = [
                                str(p) for p in paths if isinstance(p, (str, bytes))
                            ]
                    if "allow_dependency_changes" in data:
                        config["allow_dependency_changes"] = bool(data["allow_dependency_changes"])
                    if "max_runtime_seconds" in data:
                        val = data["max_runtime_seconds"]
                        if isinstance(val, (int, float)) and val > 0:
                            config["max_runtime_seconds"] = int(val)
                        elif val == 0 or val is None:
                            # Explicit 0 or null means no limit
                            config["max_runtime_seconds"] = 0
                    if "rules" in data and isinstance(data["rules"], dict):
                        rules_cfg = data["rules"]
                        rules = config["rules"]
                        if "enabled" in rules_cfg and isinstance(rules_cfg["enabled"], list):
                            # Normalize enabled rules list (filter empty strings, normalize case)
                            rules["enabled"] = [
                                str(r).lower().strip()
                                for r in rules_cfg["enabled"]
                                if r and str(r).strip()
                            ]
                        if "enforce_per_rule" in rules_cfg and isinstance(rules_cfg["enforce_per_rule"], dict):
                            # Normalize enforce_per_rule keys and values
                            rules["enforce_per_rule"] = {
                                str(k).lower().strip(): str(v).lower().strip()
                                for k, v in rules_cfg["enforce_per_rule"].items()
                                if k and v
                            }
                        if "severity_threshold" in rules_cfg:
                            # Normalize severity threshold (uppercase, validate)
                            threshold = str(rules_cfg["severity_threshold"]).upper().strip()
                            if threshold in ("INFO", "WARNING", "WARN", "ERROR"):
                                # Normalize WARN -> WARNING
                                if threshold == "WARN":
                                    threshold = "WARNING"
                                rules["severity_threshold"] = threshold
                    if "baseline_mode" in data:
                        config["baseline_mode"] = bool(data["baseline_mode"])
                    if "baseline_sha" in data:
                        # Allow null / empty string to disable
                        sha = data["baseline_sha"]
                        config["baseline_sha"] = str(sha) if sha else None
                    if "baseline_max_age_days" in data:
                        val = data["baseline_max_age_days"]
                        if isinstance(val, (int, float)) and val >= 0:
                            config["baseline_max_age_days"] = int(val)
                    if "directory_policies" in data and isinstance(data["directory_policies"], dict):
                        # Normalise keys to have trailing slash and normalize policy values
                        policies: dict[str, dict] = {}
                        for key, value in data["directory_policies"].items():
                            if not isinstance(value, dict):
                                continue
                            k = str(key).replace("\\", "/")  # Normalize path separators
                            if not k.endswith("/"):
                                k += "/"
                            
                            # Normalize policy dict
                            policy: dict[str, Any] = {}
                            
                            # Normalize severity_threshold
                            if "severity_threshold" in value:
                                threshold = str(value["severity_threshold"]).upper().strip()
                                if threshold in ("INFO", "WARNING", "WARN", "ERROR"):
                                    if threshold == "WARN":
                                        threshold = "WARNING"
                                    policy["severity_threshold"] = threshold
                            
                            # Normalize enforce_per_rule
                            if "enforce_per_rule" in value and isinstance(value["enforce_per_rule"], dict):
                                policy["enforce_per_rule"] = {
                                    str(k2).lower().strip(): str(v2).lower().strip()
                                    for k2, v2 in value["enforce_per_rule"].items()
                                    if k2 and v2
                                }
                            
                            policies[k] = policy
                        config["directory_policies"] = policies
                    if "format_after_patch" in data:
                        config["format_after_patch"] = bool(data["format_after_patch"])
                    if "max_format_expansion" in data:
                        try:
                            config["max_format_expansion"] = float(data["max_format_expansion"])
                        except (TypeError, ValueError):
                            pass
            except yaml.YAMLError as e:
                problem = getattr(e, "problem", "Invalid YAML")
                mark = getattr(e, "problem_mark", None)
                if mark is not None:
                    msg = f"{problem} at line {mark.line + 1}, column {mark.column + 1}."
                else:
                    msg = str(problem)
                raise ConfigError(config_path, [msg]) from e
            except ConfigError:
                raise
            except Exception as e:
                raise ConfigError(config_path, [f"Failed to read config: {e}"])
            break
    
    # Environment overrides
    env_max = os.getenv("FIXPOINT_MAX_DIFF_LINES")
    if env_max is not None:
        try:
            config["max_diff_lines"] = int(env_max)
        except ValueError:
            pass
    
    env_test = os.getenv("FIXPOINT_TEST_BEFORE_COMMIT", "").lower()
    if env_test in ("1", "true", "yes"):
        config["test_before_commit"] = True
    elif env_test in ("0", "false", "no"):
        config["test_before_commit"] = False
    
    env_cmd = os.getenv("FIXPOINT_TEST_COMMAND")
    if env_cmd and isinstance(env_cmd, str):
        config["test_command"] = env_cmd.strip()

    # Optional runtime override
    env_runtime = os.getenv("FIXPOINT_MAX_RUNTIME_SECONDS")
    if env_runtime is not None:
        try:
            config["max_runtime_seconds"] = int(env_runtime)
        except ValueError:
            pass
    
    return config


def get_max_diff_lines(repo_path: Path) -> int:
    """Get max allowed diff lines for auto-fix."""
    return load_config(repo_path)["max_diff_lines"]


def get_test_before_commit(repo_path: Path) -> bool:
    """Whether to run tests before committing fixes."""
    return load_config(repo_path)["test_before_commit"]


def get_test_command(repo_path: Path) -> str:
    """Command to run before committing (e.g. pytest, npm test)."""
    return load_config(repo_path)["test_command"]
