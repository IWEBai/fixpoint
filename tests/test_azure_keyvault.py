"""Tests for Azure Key Vault integration in core/github_app_auth.py.

All tests are fully offline — no real Azure credentials or network calls
are required.  azure-identity and azure-keyvault-secrets are mocked via
unittest.mock so the tests pass even when those packages are not installed.
"""
from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

import core.github_app_auth as kv_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear_kv_cache():
    """Reset the lru_cache on _load_from_key_vault between tests."""
    kv_mod._load_from_key_vault.cache_clear()


def _make_azure_mocks(secret_value: str = "s3cr3t"):
    """Return (azure_identity_mod, azure_keyvault_mod, SecretClient_class)."""
    secret_obj = MagicMock()
    secret_obj.value = secret_value

    secret_client_instance = MagicMock()
    secret_client_instance.get_secret.return_value = secret_obj

    SecretClient = MagicMock(return_value=secret_client_instance)
    DefaultAzureCredential = MagicMock()

    azure_identity = types.ModuleType("azure.identity")
    azure_identity.DefaultAzureCredential = DefaultAzureCredential

    # Build fake azure.keyvault.secrets package
    azure_kv_secrets = types.ModuleType("azure.keyvault.secrets")
    azure_kv_secrets.SecretClient = SecretClient

    azure_kv = types.ModuleType("azure.keyvault")
    azure_kv.secrets = azure_kv_secrets

    azure_root = types.ModuleType("azure")
    azure_root.identity = azure_identity
    azure_root.keyvault = azure_kv

    mods = {
        "azure": azure_root,
        "azure.identity": azure_identity,
        "azure.keyvault": azure_kv,
        "azure.keyvault.secrets": azure_kv_secrets,
    }
    return mods, DefaultAzureCredential, SecretClient, secret_client_instance


# ---------------------------------------------------------------------------
# _load_from_key_vault
# ---------------------------------------------------------------------------

class TestLoadFromKeyVault:
    def setup_method(self):
        _clear_kv_cache()

    def teardown_method(self):
        _clear_kv_cache()

    def test_returns_none_when_kv_url_not_configured(self):
        """No AZURE_KEY_VAULT_URL → skip without touching azure SDK."""
        with patch.object(kv_mod, "_KV_URL", ""):
            result = kv_mod._load_from_key_vault("any-secret")
        assert result is None

    def test_returns_secret_value_when_kv_responds(self):
        """Happy-path: SecretClient returns the secret value."""
        mods, _, _, client = _make_azure_mocks("my-webhook-secret")
        with patch.object(kv_mod, "_KV_URL", "https://railo-kv.vault.azure.net"), \
             patch.dict(sys.modules, mods):
            result = kv_mod._load_from_key_vault("github-webhook-secret")
        assert result == "my-webhook-secret"
        client.get_secret.assert_called_once_with("github-webhook-secret")

    def test_returns_none_on_import_error(self):
        """azure packages not installed → ImportError → return None gracefully."""
        # Force ImportError by ensuring azure.identity is absent
        with patch.object(kv_mod, "_KV_URL", "https://railo-kv.vault.azure.net"), \
             patch.dict(sys.modules, {"azure.identity": None, "azure.keyvault.secrets": None}):
            result = kv_mod._load_from_key_vault("any-secret")
        # None because ImportError is swallowed
        assert result is None

    def test_returns_none_on_auth_failure(self):
        """Network / auth failures → return None without raising."""
        mods, _, SecretClient, _ = _make_azure_mocks()
        # Make get_secret raise an exception simulating auth failure
        SecretClient.return_value.get_secret.side_effect = Exception("AuthenticationFailed")
        with patch.object(kv_mod, "_KV_URL", "https://railo-kv.vault.azure.net"), \
             patch.dict(sys.modules, mods):
            result = kv_mod._load_from_key_vault("any-secret")
        assert result is None

    def test_returns_none_when_secret_value_empty(self):
        """Key Vault secret exists but has an empty value → return None."""
        mods, _, _, client = _make_azure_mocks(secret_value="")
        with patch.object(kv_mod, "_KV_URL", "https://railo-kv.vault.azure.net"), \
             patch.dict(sys.modules, mods):
            result = kv_mod._load_from_key_vault("empty-secret")
        assert result is None

    def test_caches_result_on_second_call(self):
        """lru_cache means SecretClient.get_secret is called only once."""
        mods, _, _, client = _make_azure_mocks("cached-value")
        with patch.object(kv_mod, "_KV_URL", "https://railo-kv.vault.azure.net"), \
             patch.dict(sys.modules, mods):
            first = kv_mod._load_from_key_vault("my-secret")
            second = kv_mod._load_from_key_vault("my-secret")
        assert first == second == "cached-value"
        assert client.get_secret.call_count == 1  # only called once, then cached

    def test_different_secret_names_make_separate_calls(self):
        """Cache key includes secret name — different names hit the SDK separately."""
        mods, _, _, client = _make_azure_mocks("val")
        with patch.object(kv_mod, "_KV_URL", "https://railo-kv.vault.azure.net"), \
             patch.dict(sys.modules, mods):
            kv_mod._load_from_key_vault("secret-a")
            kv_mod._load_from_key_vault("secret-b")
        assert client.get_secret.call_count == 2


# ---------------------------------------------------------------------------
# get_webhook_secret_from_kv
# ---------------------------------------------------------------------------

class TestGetWebhookSecretFromKv:
    def setup_method(self):
        _clear_kv_cache()

    def teardown_method(self):
        _clear_kv_cache()

    def test_returns_none_without_kv_url(self):
        with patch.object(kv_mod, "_KV_URL", ""):
            assert kv_mod.get_webhook_secret_from_kv() is None

    def test_returns_secret_from_kv(self):
        mods, _, _, _ = _make_azure_mocks("webhook-secret-xyz")
        with patch.object(kv_mod, "_KV_URL", "https://railo-kv.vault.azure.net"), \
             patch.object(kv_mod, "_KV_SECRET_WEBHOOK", "github-webhook-secret"), \
             patch.dict(sys.modules, mods):
            result = kv_mod.get_webhook_secret_from_kv()
        assert result == "webhook-secret-xyz"

    def test_returns_none_when_kv_unavailable(self):
        """If Key Vault SDK is absent, returns None without raising."""
        with patch.object(kv_mod, "_KV_URL", "https://railo-kv.vault.azure.net"), \
             patch.dict(sys.modules, {"azure.identity": None, "azure.keyvault.secrets": None}):
            result = kv_mod.get_webhook_secret_from_kv()
        assert result is None


# ---------------------------------------------------------------------------
# get_secret_from_key_vault (public wrapper)
# ---------------------------------------------------------------------------

class TestGetSecretFromKeyVault:
    def setup_method(self):
        _clear_kv_cache()

    def teardown_method(self):
        _clear_kv_cache()

    def test_delegates_to_load_from_key_vault(self):
        with patch.object(kv_mod, "_load_from_key_vault", return_value="pg-conn-string") as m:
            result = kv_mod.get_secret_from_key_vault("pg-conn")
        m.assert_called_once_with("pg-conn")
        assert result == "pg-conn-string"

    def test_returns_none_when_not_configured(self):
        with patch.object(kv_mod, "_KV_URL", ""):
            assert kv_mod.get_secret_from_key_vault("anything") is None


# ---------------------------------------------------------------------------
# _load_private_key — Key Vault priority
# ---------------------------------------------------------------------------

class TestLoadPrivateKeyAzurePriority:
    def setup_method(self):
        _clear_kv_cache()

    def teardown_method(self):
        _clear_kv_cache()

    def test_uses_kv_when_configured(self, monkeypatch):
        """Key Vault is tried first; if it returns a value, it is used."""
        fake_pem = "-----BEGIN RSA PRIVATE KEY-----\nMIItest\n-----END RSA PRIVATE KEY-----"
        mods, _, _, _ = _make_azure_mocks(fake_pem)
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "")
        with patch.object(kv_mod, "_KV_URL", "https://railo-kv.vault.azure.net"), \
             patch.dict(sys.modules, mods):
            result = kv_mod._load_private_key()
        assert result == fake_pem

    def test_falls_back_to_env_when_kv_not_configured(self, monkeypatch):
        """When AZURE_KEY_VAULT_URL is absent, reads from env var."""
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "env-pem-value")
        with patch.object(kv_mod, "_KV_URL", ""):
            result = kv_mod._load_private_key()
        assert result == "env-pem-value"

    def test_falls_back_to_env_when_kv_returns_none(self, monkeypatch):
        """Key Vault configured but returns nothing → fall back to env var."""
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "fallback-pem")
        mods, _, _, client = _make_azure_mocks("")  # empty secret
        with patch.object(kv_mod, "_KV_URL", "https://railo-kv.vault.azure.net"), \
             patch.dict(sys.modules, mods):
            result = kv_mod._load_private_key()
        assert result == "fallback-pem"

    def test_returns_none_when_no_sources(self, monkeypatch, tmp_path):
        """All sources exhausted → None."""
        monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY", raising=False)
        monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY_PATH", raising=False)
        monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY_PEM_BASE64", raising=False)
        with patch.object(kv_mod, "_KV_URL", ""):
            result = kv_mod._load_private_key()
        assert result is None


# ---------------------------------------------------------------------------
# _get_webhook_secrets (webhook/server.py) — KV-first ordering
# ---------------------------------------------------------------------------

class TestGetWebhookSecretOrdering:
    def setup_method(self):
        _clear_kv_cache()

    def teardown_method(self):
        _clear_kv_cache()

    def test_kv_secret_is_first_in_list(self, monkeypatch):
        """KV secret appears before the env-var secret in the list."""
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "env-secret")
        with patch("core.github_app_auth.get_webhook_secret_from_kv", return_value="kv-secret"):
            from webhook.server import _get_webhook_secrets
            secrets = _get_webhook_secrets()
        assert secrets[0] == "kv-secret"
        assert "env-secret" in secrets

    def test_env_var_used_when_kv_unavailable(self, monkeypatch):
        """Falls back to env var when Key Vault returns None."""
        monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "only-env-secret")
        with patch("core.github_app_auth.get_webhook_secret_from_kv", return_value=None):
            from webhook.server import _get_webhook_secrets
            secrets = _get_webhook_secrets()
        assert "only-env-secret" in secrets

    def test_empty_list_when_no_secrets_configured(self, monkeypatch):
        """No KV, no env vars → empty list (HMAC validation will reject all requests)."""
        monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
        monkeypatch.delenv("GITHUB_APP_WEBHOOK_SECRET", raising=False)
        monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
        with patch("core.github_app_auth.get_webhook_secret_from_kv", return_value=None):
            from webhook.server import _get_webhook_secrets
            secrets = _get_webhook_secrets()
        assert secrets == []


# ---------------------------------------------------------------------------
# worker-app.yaml structural validation
# ---------------------------------------------------------------------------

class TestWorkerAppYaml:
    """Validate that worker-app.yaml references the expected Key Vault secrets."""

    REQUIRED_KV_SECRETS = {
        "pg-conn",
        "redis-url",
        "github-app-id",
        "github-private-key",
        "github-webhook-secret",
    }

    @pytest.fixture(scope="class")
    def yaml_text(self):
        import pathlib
        path = pathlib.Path(__file__).parent.parent / "worker-app.yaml"
        return path.read_text(encoding="utf-8")

    def test_all_required_secrets_present(self, yaml_text):
        """Every expected secret name appears in the YAML."""
        for secret in self.REQUIRED_KV_SECRETS:
            assert secret in yaml_text, f"Missing Key Vault secret reference: {secret}"

    def test_acr_registry_referenced(self, yaml_text):
        """Container image is pulled from the Railo ACR."""
        assert "railoregistry.azurecr.io" in yaml_text

    def test_key_vault_url_referenced(self, yaml_text):
        """Key Vault vault URL appears in the YAML."""
        assert "railo-kv.vault.azure.net" in yaml_text

    def test_managed_identity_used(self, yaml_text):
        """Secrets are bound via a User-Assigned Managed Identity (not a password)."""
        assert "UserAssigned" in yaml_text or "userAssignedIdentities" in yaml_text

    def test_no_plaintext_secrets(self, yaml_text):
        """No raw secret values appear in the YAML — only Key Vault refs."""
        # Ensure the YAML contains keyVaultUrl references (not inline values)
        assert "keyVaultUrl" in yaml_text
        # No bearer-token-like strings or PEM headers
        assert "-----BEGIN" not in yaml_text
        assert "ghp_" not in yaml_text  # no GitHub PATs
