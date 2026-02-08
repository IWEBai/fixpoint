"""
Tests for security module.
"""
import hmac
import hashlib
import os
from unittest.mock import patch
from core.security import (
    verify_webhook_signature,
    is_allowed_event_type,
    is_allowed_pr_action,
    check_replay_protection,
    validate_webhook_request,
)


class TestVerifyWebhookSignature:
    """Tests for webhook signature verification."""
    
    def test_valid_signature_returns_true(self):
        """Should return True for valid HMAC-SHA256 signature."""
        secret = "test_secret"
        payload = b'{"action": "opened"}'
        
        # Generate valid signature
        expected = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        signature = f"sha256={expected}"
        
        result = verify_webhook_signature(payload, signature, secret)
        assert result is True
    
    def test_invalid_signature_returns_false(self):
        """Should return False for invalid signature."""
        secret = "test_secret"
        payload = b'{"action": "opened"}'
        signature = "sha256=invalid_signature"
        
        result = verify_webhook_signature(payload, signature, secret)
        assert result is False
    
    def test_missing_signature_returns_false(self):
        """Should return False when signature is empty."""
        secret = "test_secret"
        payload = b'{"action": "opened"}'
        
        result = verify_webhook_signature(payload, "", secret)
        assert result is False
    
    def test_missing_secret_returns_false(self):
        """Should return False when secret is missing (security fix)."""
        payload = b'{"action": "opened"}'
        signature = "sha256=anything"
        
        # Without SKIP_WEBHOOK_VERIFICATION, missing secret should fail
        with patch.dict(os.environ, {}, clear=True):
            result = verify_webhook_signature(payload, signature, "")
            assert result is False
    
    def test_skip_verification_env_var(self):
        """Should skip verification only when explicitly requested."""
        payload = b'{"action": "opened"}'
        
        # With SKIP_WEBHOOK_VERIFICATION=true, should pass without secret
        with patch.dict(os.environ, {"SKIP_WEBHOOK_VERIFICATION": "true"}):
            result = verify_webhook_signature(payload, "", "")
            assert result is True
    
    def test_wrong_signature_prefix_returns_false(self):
        """Should return False when signature doesn't start with sha256=."""
        secret = "test_secret"
        payload = b'{"action": "opened"}'
        signature = "sha1=something"
        
        result = verify_webhook_signature(payload, signature, secret)
        assert result is False


class TestEventTypeFiltering:
    """Tests for event type allowlist."""
    
    def test_pull_request_event_allowed(self):
        """Should allow pull_request events."""
        assert is_allowed_event_type("pull_request") is True
    
    def test_push_event_not_allowed(self):
        """Should not allow push events."""
        assert is_allowed_event_type("push") is False
    
    def test_issue_event_not_allowed(self):
        """Should not allow issue events."""
        assert is_allowed_event_type("issues") is False
    
    def test_empty_event_not_allowed(self):
        """Should not allow empty event type."""
        assert is_allowed_event_type("") is False


class TestPRActionFiltering:
    """Tests for PR action allowlist."""
    
    def test_opened_action_allowed(self):
        """Should allow 'opened' action."""
        assert is_allowed_pr_action("opened") is True
    
    def test_synchronize_action_allowed(self):
        """Should allow 'synchronize' action."""
        assert is_allowed_pr_action("synchronize") is True
    
    def test_closed_action_not_allowed(self):
        """Should not allow 'closed' action."""
        assert is_allowed_pr_action("closed") is False
    
    def test_merged_action_not_allowed(self):
        """Should not allow 'merged' action."""
        assert is_allowed_pr_action("merged") is False


class TestReplayProtection:
    """Tests for replay protection."""
    
    def test_first_delivery_not_rejected(self):
        """First time delivery should not be rejected."""
        delivery_id = "unique-delivery-id-12345"
        result = check_replay_protection(delivery_id)
        assert result is False  # Not a replay
    
    def test_missing_delivery_id_not_rejected(self):
        """Missing delivery ID should not be rejected (can't protect)."""
        result = check_replay_protection("")
        assert result is False


class TestValidateWebhookRequest:
    """Tests for comprehensive webhook validation."""
    
    def test_valid_request_passes(self):
        """Should pass valid webhook request."""
        secret = "test_secret"
        payload = b'{"action": "opened"}'
        
        signature = "sha256=" + hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        is_valid, error = validate_webhook_request(
            payload_body=payload,
            signature=signature,
            event_type="pull_request",
            delivery_id="unique-id-456",
            secret=secret,
        )
        
        assert is_valid is True
        assert error is None
    
    def test_invalid_signature_fails(self):
        """Should fail with invalid signature."""
        is_valid, error = validate_webhook_request(
            payload_body=b'{"action": "opened"}',
            signature="sha256=invalid",
            event_type="pull_request",
            delivery_id="unique-id-789",
            secret="secret",
        )
        
        assert is_valid is False
        assert "signature" in error.lower()
    
    def test_disallowed_event_fails(self):
        """Should fail with disallowed event type."""
        secret = "test_secret"
        payload = b'{"action": "opened"}'
        
        signature = "sha256=" + hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        is_valid, error = validate_webhook_request(
            payload_body=payload,
            signature=signature,
            event_type="push",  # Not allowed
            delivery_id="unique-id-101",
            secret=secret,
        )
        
        assert is_valid is False
        assert "not allowed" in error.lower()
