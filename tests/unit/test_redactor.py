"""Unit tests for sensitive data redaction under Privacy & Security principles."""

from kaufee.safety.redactor import redact_data, redact_sensitive_text


def test_redact_api_keys():
    text = "Connecting with sk-proj-1234567890abcdef1234567890 and gh_p1234567890abcdef1234567890abcdef1234"
    redacted = redact_sensitive_text(text)
    assert "sk-proj" not in redacted
    assert "[REDACTED_API_KEY]" in redacted or "[REDACTED" in redacted


def test_redact_passwords_and_tokens():
    text = "Config: password='supersecret123', token=\"my-secret-token-xyz\""
    redacted = redact_sensitive_text(text)
    assert "supersecret123" not in redacted
    assert "my-secret-token-xyz" not in redacted
    assert "[REDACTED_SECRET]" in redacted


def test_redact_private_keys():
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...\n-----END RSA PRIVATE KEY-----"
    redacted = redact_sensitive_text(text)
    assert "MIIEowIBAAKCAQEA0" not in redacted
    assert "[REDACTED_PRIVATE_KEY]" in redacted


def test_redact_credit_cards_and_ssn():
    text = "User info: card 4532 0150 1234 5678, SSN 123-45-6789"
    redacted = redact_sensitive_text(text)
    assert "4532 0150 1234 5678" not in redacted
    assert "123-45-6789" not in redacted
    assert "[REDACTED_CARD]" in redacted
    assert "[REDACTED_SSN]" in redacted


def test_redact_nested_structures():
    nested = {
        "user": "Alice",
        "secret_info": {
            "api_key": "sk-12345678901234567890123456789012",
            "password": "Password123!",
            "tags": ["prod", "Bearer abcdef1234567890ghijklmnop"],
        },
    }
    redacted = redact_data(nested)
    assert redacted["user"] == "Alice"
    assert "sk-1234567890" not in str(redacted)
    assert "Password123!" not in str(redacted)
    assert "[REDACTED_SECRET]" in redacted["secret_info"]["password"]
