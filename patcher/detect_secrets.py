"""
Hardcoded secrets detection using AST and regex patterns.
Detects API keys, passwords, tokens, and other sensitive values in Python code.
"""
from __future__ import annotations

import ast
import re
from typing import List, Optional, Tuple
from dataclasses import dataclass


# Patterns for detecting hardcoded secrets
SECRET_PATTERNS = {
    # AWS
    "aws_access_key": r'AKIA[0-9A-Z]{16}',
    "aws_secret_key": r'[A-Za-z0-9/+=]{40}',
    
    # GitHub
    "github_token": r'gh[pousr]_[A-Za-z0-9_]{36,}',
    "github_oauth": r'gho_[A-Za-z0-9]{36}',
    
    # Generic API keys
    "api_key_generic": r'[aA][pP][iI][-_]?[kK][eE][yY]["\s:=]+["\']?[A-Za-z0-9_\-]{20,}',
    
    # Slack
    "slack_token": r'xox[baprs]-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24}',
    "slack_webhook": r'https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+',
    
    # Stripe
    "stripe_key": r'sk_live_[0-9a-zA-Z]{24,}',
    "stripe_restricted": r'rk_live_[0-9a-zA-Z]{24,}',
    
    # Database connection strings
    "postgres_uri": r'postgres(ql)?://[^:]+:[^@]+@[^/]+/\w+',
    "mysql_uri": r'mysql://[^:]+:[^@]+@[^/]+/\w+',
    "mongodb_uri": r'mongodb(\+srv)?://[^:]+:[^@]+@[^/]+',
    
    # JWT secrets (long random strings assigned to secret variables)
    "jwt_secret": r'["\'][A-Za-z0-9+/=]{32,}["\']',
    
    # Private keys
    "private_key": r'-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----',
    
    # Google
    "google_api": r'AIza[0-9A-Za-z_-]{35}',
    "google_oauth": r'[0-9]+-[0-9A-Za-z_]{32}\.apps\.googleusercontent\.com',
    
    # SendGrid
    "sendgrid_key": r'SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}',
    
    # Twilio
    "twilio_sid": r'AC[a-f0-9]{32}',
    "twilio_token": r'[a-f0-9]{32}',
    
    # Mailgun
    "mailgun_key": r'key-[0-9a-zA-Z]{32}',
    
    # Generic patterns
    "bearer_token": r'[Bb]earer\s+[A-Za-z0-9_\-.~+/]+=*',
    "basic_auth": r'[Bb]asic\s+[A-Za-z0-9+/]+=*',
}

# Variable names that suggest secrets
SECRET_VARIABLE_NAMES = {
    "password", "passwd", "pwd", "pass",
    "secret", "secret_key", "secretkey",
    "api_key", "apikey", "api_secret",
    "access_key", "accesskey",
    "private_key", "privatekey",
    "auth_token", "authtoken", "token",
    "credentials", "creds",
    "db_password", "database_password",
    "encryption_key", "encryptionkey",
    "signing_key", "signingkey",
    "client_secret", "clientsecret",
    "app_secret", "appsecret",
}

# Values that are likely placeholders (not real secrets)
# These patterns must match the ENTIRE value or a clear placeholder prefix
PLACEHOLDER_PATTERNS = [
    r'^your[_-]?(password|secret|key|token|api)',  # your_password, your-secret
    r'^test[_-]?(password|secret|key|token|api)',  # test_password
    r'^fake[_-]?(password|secret|key|token|api)',  # fake_secret
    r'^dummy[_-]?(password|secret|key|token|api)',  # dummy_key
    r'^example[_-]?(password|secret|key|token|api)',  # example_token
    r'^sample[_-]?(password|secret|key|token|api)',  # sample_api
    r'^xxx+$',  # xxxx
    r'^\*+$',  # ****
    r'^placeholder',  # placeholder
    r'^changeme$',  # changeme
    r'^todo$',  # todo
    r'^fixme$',  # fixme
    r'^replace[_-]?me',  # replace_me
    r'^insert[_-]?here',  # insert_here
    r'^your[_-]?.*[_-]?here$',  # your_key_here
    r'<[^>]+>',  # <YOUR_KEY_HERE>
    r'\{\{[^}]+\}\}',  # {{ template }}
    r'\$\{[^}]+\}',  # ${ENV_VAR}
    r'%\([^)]+\)s',  # %(var)s
]


@dataclass
class HardcodedSecret:
    """Represents a detected hardcoded secret."""
    secret_type: str  # e.g., "aws_access_key", "password_assignment"
    var_name: str  # The variable name
    value: str  # The secret value (masked in output)
    line_number: int  # 1-based line number
    column: int  # Column offset
    confidence: str  # "high", "medium", "low"
    suggested_env_var: str  # Suggested environment variable name


def _is_placeholder(value: str) -> bool:
    """Check if a value looks like a placeholder, not a real secret."""
    value_lower = value.lower()
    for pattern in PLACEHOLDER_PATTERNS:
        if re.search(pattern, value_lower, re.IGNORECASE):
            return True
    
    # Very short values are likely placeholders
    if len(value) < 8:
        return True
    
    # All same character
    if len(set(value)) <= 2:
        return True
    
    return False


def _mask_secret(value: str, show_chars: int = 4) -> str:
    """Mask a secret value for safe display."""
    if len(value) <= show_chars * 2:
        return "*" * len(value)
    return value[:show_chars] + "*" * (len(value) - show_chars * 2) + value[-show_chars:]


def _suggest_env_var(var_name: str) -> str:
    """Suggest an environment variable name based on the variable name."""
    # Convert to uppercase and replace non-alphanumeric with underscore
    env_var = re.sub(r'[^A-Za-z0-9]', '_', var_name).upper()
    # Remove consecutive underscores
    env_var = re.sub(r'_+', '_', env_var)
    # Remove leading/trailing underscores
    env_var = env_var.strip('_')
    return env_var or "SECRET_VALUE"


def _check_value_patterns(value: str) -> Optional[Tuple[str, str]]:
    """Check if a string value matches known secret patterns."""
    for secret_type, pattern in SECRET_PATTERNS.items():
        if re.search(pattern, value):
            return secret_type, "high"
    return None


def find_hardcoded_secrets(code: str) -> List[HardcodedSecret]:
    """
    Find hardcoded secrets in Python code using AST analysis.
    
    Args:
        code: Python source code
    
    Returns:
        List of HardcodedSecret objects
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    
    secrets = []
    
    for node in ast.walk(tree):
        # Check assignments: password = "secret123"
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    var_name = target.id.lower()
                    
                    # Check if variable name suggests a secret
                    if any(secret_name in var_name for secret_name in SECRET_VARIABLE_NAMES):
                        # Get the assigned value
                        value = None
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                            value = node.value.value
                        elif isinstance(node.value, ast.Str):  # Python < 3.8
                            value = node.value.s
                        
                        if value and not _is_placeholder(value):
                            # Check for pattern match
                            pattern_match = _check_value_patterns(value)
                            confidence = pattern_match[1] if pattern_match else "medium"
                            secret_type = pattern_match[0] if pattern_match else "suspicious_assignment"
                            
                            secrets.append(HardcodedSecret(
                                secret_type=secret_type,
                                var_name=target.id,
                                value=_mask_secret(value),
                                line_number=node.lineno,
                                column=node.col_offset,
                                confidence=confidence,
                                suggested_env_var=_suggest_env_var(target.id),
                            ))
        
        # Check dictionary literals: {"password": "secret123"}
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    key_name = key.value.lower()
                elif isinstance(key, ast.Str):
                    key_name = key.s.lower()
                else:
                    continue
                
                if any(secret_name in key_name for secret_name in SECRET_VARIABLE_NAMES):
                    val_str = None
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        val_str = value.value
                    elif isinstance(value, ast.Str):
                        val_str = value.s
                    
                    if val_str and not _is_placeholder(val_str):
                        pattern_match = _check_value_patterns(val_str)
                        confidence = pattern_match[1] if pattern_match else "medium"
                        secret_type = pattern_match[0] if pattern_match else "suspicious_dict_value"
                        
                        secrets.append(HardcodedSecret(
                            secret_type=secret_type,
                            var_name=key.value if isinstance(key, ast.Constant) else key.s,
                            value=_mask_secret(val_str),
                            line_number=node.lineno,
                            column=node.col_offset,
                            confidence=confidence,
                            suggested_env_var=_suggest_env_var(key.value if isinstance(key, ast.Constant) else key.s),
                        ))
        
        # Check function calls with keyword arguments: connect(password="secret")
        elif isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg and keyword.arg.lower() in SECRET_VARIABLE_NAMES:
                    val_str = None
                    if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                        val_str = keyword.value.value
                    elif isinstance(keyword.value, ast.Str):
                        val_str = keyword.value.s
                    
                    if val_str and not _is_placeholder(val_str):
                        pattern_match = _check_value_patterns(val_str)
                        confidence = pattern_match[1] if pattern_match else "medium"
                        secret_type = pattern_match[0] if pattern_match else "suspicious_kwarg"
                        
                        secrets.append(HardcodedSecret(
                            secret_type=secret_type,
                            var_name=keyword.arg,
                            value=_mask_secret(val_str),
                            line_number=node.lineno,
                            column=node.col_offset,
                            confidence=confidence,
                            suggested_env_var=_suggest_env_var(keyword.arg),
                        ))
    
    # Also scan for high-confidence patterns anywhere in the code
    for i, line in enumerate(code.split('\n'), 1):
        for secret_type, pattern in SECRET_PATTERNS.items():
            # Skip patterns we likely already caught via AST
            if secret_type in {"jwt_secret"}:
                continue
            
            matches = re.finditer(pattern, line)
            for match in matches:
                value = match.group(0)
                if not _is_placeholder(value):
                    # Check if we already have this line
                    if not any(s.line_number == i for s in secrets):
                        secrets.append(HardcodedSecret(
                            secret_type=secret_type,
                            var_name="(inline)",
                            value=_mask_secret(value),
                            line_number=i,
                            column=match.start(),
                            confidence="high",
                            suggested_env_var=secret_type.upper(),
                        ))
    
    return secrets


def has_hardcoded_secrets(code: str) -> bool:
    """Quick check if code contains hardcoded secrets."""
    return len(find_hardcoded_secrets(code)) > 0
