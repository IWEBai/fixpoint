"""
Integration tests for the webhook server flow.
"""
import pytest
import json
import hmac
import hashlib
import os
import importlib
from unittest.mock import patch
from pathlib import Path

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestWebhookIntegration:
    """Integration tests for webhook processing flow."""
    
    @pytest.fixture
    def app(self):
        """Create Flask test client."""
        from webhook.server import app
        app.config['TESTING'] = True
        return app.test_client()
    
    @pytest.fixture
    def valid_pr_payload(self):
        """Create a valid PR webhook payload."""
        return {
            "action": "opened",
            "number": 1,
            "pull_request": {
                "number": 1,
                "head": {
                    "ref": "feature-branch",
                    "sha": "abc123def456",
                    "repo": {
                        "full_name": "owner/repo",
                        "clone_url": "https://github.com/owner/repo.git",
                        "fork": False
                    }
                },
                "base": {
                    "ref": "main",
                    "repo": {
                        "full_name": "owner/repo"
                    }
                },
                "html_url": "https://github.com/owner/repo/pull/1"
            },
            "repository": {
                "full_name": "owner/repo",
                "name": "repo",
                "owner": {
                    "login": "owner"
                },
                "clone_url": "https://github.com/owner/repo.git"
            }
        }
    
    def _sign_payload(self, payload: dict, secret: str) -> str:
        """Generate GitHub webhook signature."""
        body = json.dumps(payload).encode()
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return f"sha256={sig}"
    
    def test_health_check(self, app):
        """Health endpoint should return 200."""
        response = app.get('/health')
        assert response.status_code == 200
        assert response.json['status'] == 'healthy'

    def test_landing_page(self, app):
        """Landing page should return 200 and contain install CTA."""
        response = app.get('/')
        assert response.status_code == 200
        assert b'Install Fixpoint' in response.data or b'install' in response.data.lower()

    def test_privacy_page(self, app):
        """Privacy policy page should return 200."""
        response = app.get('/privacy')
        assert response.status_code == 200
        assert b'Privacy' in response.data

    def test_dashboard_responds(self, app):
        """Dashboard endpoint responds (200 when unconfigured, 302 when OAuth redirect)."""
        response = app.get('/dashboard')
        assert response.status_code in (200, 302)
        if response.status_code == 200:
            assert b'Dashboard' in response.data
    
    @patch.dict(os.environ, {"SKIP_WEBHOOK_VERIFICATION": "true"})
    def test_webhook_rejects_invalid_event_type(self, app, valid_pr_payload):
        """Should reject non-pull_request events."""
        response = app.post(
            '/webhook',
            data=json.dumps(valid_pr_payload),
            headers={
                'Content-Type': 'application/json',
                'X-GitHub-Event': 'push',  # Not pull_request
                'X-GitHub-Delivery': 'test-delivery-1',
            }
        )
        
        assert response.status_code == 401
        assert "not allowed" in response.json.get('error', '').lower()
    
    @patch.dict(os.environ, {"SKIP_WEBHOOK_VERIFICATION": "true"})
    def test_webhook_accepts_pull_request_event(self, app, valid_pr_payload):
        """Should accept pull_request events."""
        with patch('webhook.server.process_pr_webhook') as mock_process:
            mock_process.return_value = {"status": "success", "message": "Processed"}
            
            response = app.post(
                '/webhook',
                data=json.dumps(valid_pr_payload),
                headers={
                    'Content-Type': 'application/json',
                    'X-GitHub-Event': 'pull_request',
                    'X-GitHub-Delivery': 'test-delivery-2',
                }
            )
            
            assert response.status_code == 200
    
    @patch.dict(os.environ, {"SKIP_WEBHOOK_VERIFICATION": "true"})
    def test_webhook_ignores_closed_action(self, app, valid_pr_payload):
        """Should ignore PR closed action."""
        valid_pr_payload["action"] = "closed"
        
        response = app.post(
            '/webhook',
            data=json.dumps(valid_pr_payload),
            headers={
                'Content-Type': 'application/json',
                'X-GitHub-Event': 'pull_request',
                'X-GitHub-Delivery': 'test-delivery-3',
            }
        )
        
        assert response.status_code == 200
        assert response.json['status'] == 'ignored'
    
    def test_webhook_requires_signature(self, app, valid_pr_payload):
        """Should require valid signature when secret is set."""
        with patch.dict(os.environ, {"WEBHOOK_SECRET": "test-secret"}, clear=False):
            # No signature provided
            response = app.post(
                '/webhook',
                data=json.dumps(valid_pr_payload),
                headers={
                    'Content-Type': 'application/json',
                    'X-GitHub-Event': 'pull_request',
                    'X-GitHub-Delivery': 'test-delivery-4',
                }
            )
            
            assert response.status_code == 401
    
    def test_webhook_validates_signature(self, valid_pr_payload):
        """Should validate correct signature."""
        secret = "test-secret"
        
        # Need to patch WEBHOOK_SECRET before importing the app
        with patch.dict(os.environ, {"WEBHOOK_SECRET": secret}, clear=False):
            # Reload the module to pick up the new env var
            import webhook.server
            import importlib
            importlib.reload(webhook.server)
            
            app = webhook.server.app.test_client()
            
            with patch.object(webhook.server, 'process_pr_webhook') as mock_process:
                mock_process.return_value = {"status": "success"}
                
                body = json.dumps(valid_pr_payload)
                signature = self._sign_payload(valid_pr_payload, secret)
                
                response = app.post(
                    '/webhook',
                    data=body,
                    headers={
                        'Content-Type': 'application/json',
                        'X-GitHub-Event': 'pull_request',
                        'X-GitHub-Delivery': 'test-delivery-5',
                        'X-Hub-Signature-256': signature,
                    }
                )
                
                assert response.status_code == 200
    
    def test_webhook_rejects_invalid_json(self):
        """Should reject invalid JSON payload."""
        with patch.dict(os.environ, {"SKIP_WEBHOOK_VERIFICATION": "true"}):
            # Reload the module to pick up the env var change
            import webhook.server
            importlib.reload(webhook.server)
            
            app = webhook.server.app.test_client()
            
            response = app.post(
                '/webhook',
                data='not valid json',
                headers={
                    'Content-Type': 'application/json',
                    'X-GitHub-Event': 'pull_request',
                    'X-GitHub-Delivery': 'test-delivery-6',
                }
            )
            
            assert response.status_code == 400


class TestRepoAllowlistDenylist:
    """Tests for repository allowlist/denylist functionality."""
    
    def test_repo_denied_when_in_denylist(self):
        """Should deny repos in DENIED_REPOS."""
        from core.security import is_repo_allowed
        
        with patch.dict(os.environ, {"DENIED_REPOS": "owner/bad-repo,owner/another-bad"}):
            is_allowed, reason = is_repo_allowed("owner/bad-repo")
            
            assert is_allowed is False
            assert "deny list" in reason.lower()
    
    def test_repo_allowed_when_not_in_denylist(self):
        """Should allow repos not in denylist."""
        from core.security import is_repo_allowed
        
        with patch.dict(os.environ, {"DENIED_REPOS": "owner/bad-repo"}):
            is_allowed, reason = is_repo_allowed("owner/good-repo")
            
            assert is_allowed is True
    
    def test_repo_allowed_when_in_allowlist(self):
        """Should allow repos in ALLOWED_REPOS."""
        from core.security import is_repo_allowed
        
        with patch.dict(os.environ, {"ALLOWED_REPOS": "owner/good-repo,owner/another-good"}):
            is_allowed, reason = is_repo_allowed("owner/good-repo")
            
            assert is_allowed is True
    
    def test_repo_denied_when_not_in_allowlist(self):
        """Should deny repos not in allowlist when allowlist is set."""
        from core.security import is_repo_allowed
        
        with patch.dict(os.environ, {"ALLOWED_REPOS": "owner/good-repo"}):
            is_allowed, reason = is_repo_allowed("owner/other-repo")
            
            assert is_allowed is False
            assert "allow list" in reason.lower()
    
    def test_denylist_takes_precedence(self):
        """Denylist should take precedence over allowlist."""
        from core.security import is_repo_allowed
        
        with patch.dict(os.environ, {
            "ALLOWED_REPOS": "owner/repo",
            "DENIED_REPOS": "owner/repo"
        }):
            is_allowed, reason = is_repo_allowed("owner/repo")
            
            assert is_allowed is False
            assert "deny" in reason.lower()
    
    def test_all_repos_allowed_when_no_lists(self):
        """Should allow all repos when no lists are configured."""
        from core.security import is_repo_allowed
        
        with patch.dict(os.environ, {}, clear=True):
            # Make sure env vars are not set
            os.environ.pop("ALLOWED_REPOS", None)
            os.environ.pop("DENIED_REPOS", None)
            
            is_allowed, reason = is_repo_allowed("any/repo")
            
            assert is_allowed is True
    
    def test_case_insensitive_matching(self):
        """Should match repos case-insensitively."""
        from core.security import is_repo_allowed
        
        with patch.dict(os.environ, {"DENIED_REPOS": "Owner/Repo"}):
            is_allowed, _ = is_repo_allowed("owner/repo")
            
            assert is_allowed is False
    
    def test_empty_repo_name_denied(self):
        """Should deny empty repo names."""
        from core.security import is_repo_allowed
        
        is_allowed, reason = is_repo_allowed("")
        
        assert is_allowed is False
        assert "empty" in reason.lower()
