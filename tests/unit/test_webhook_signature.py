import hashlib
import hmac

import app.main as main_module


def test_verify_signature_valid_and_invalid_matches_sha256(monkeypatch):
    monkeypatch.setattr(main_module, "WEBHOOK_SECRET", "test-secret")

    body = b'{"action":"opened"}'
    digest = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
    signature = f"sha256={digest}"

    assert main_module.verify_signature(body, signature) is True
    assert main_module.verify_signature(body, "sha256=deadbeef") is False
    assert main_module.verify_signature(b'{"action":"closed"}', signature) is False
