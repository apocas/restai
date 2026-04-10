"""Tests for crypto utility functions."""
from restai.utils.crypto import (
    LLM_SENSITIVE_KEYS,
    PROJECT_SENSITIVE_KEYS,
    SYNC_SOURCE_SENSITIVE_KEYS,
    decrypt_field,
    decrypt_sensitive_options,
    encrypt_field,
    encrypt_sensitive_options,
    generate_recovery_codes,
    hash_api_key,
    hash_recovery_code,
)


def test_encrypt_decrypt_field_round_trip():
    plaintext = "my-secret-value"
    encrypted = encrypt_field(plaintext)
    assert encrypted != plaintext
    assert encrypted.startswith("$ENC$")
    decrypted = decrypt_field(encrypted)
    assert decrypted == plaintext


def test_decrypt_field_on_plaintext_returns_as_is():
    """Backward compatibility: plaintext without $ENC$ prefix is returned unchanged."""
    raw = "legacy-plaintext-key"
    assert decrypt_field(raw) == raw


def test_encrypt_field_is_idempotent():
    """Calling encrypt_field twice should not double-encrypt."""
    plaintext = "idempotent-test"
    once = encrypt_field(plaintext)
    twice = encrypt_field(once)
    assert once == twice
    assert decrypt_field(twice) == plaintext


def test_encrypt_decrypt_sensitive_options_with_project_keys():
    opts = {
        "telegram_token": "tok_123",
        "connection": "postgresql://user:pass@host/db",
        "unrelated_key": "should-stay-plain",
    }
    encrypted = encrypt_sensitive_options(opts, PROJECT_SENSITIVE_KEYS)

    assert encrypted["telegram_token"].startswith("$ENC$")
    assert encrypted["connection"].startswith("$ENC$")
    assert encrypted["unrelated_key"] == "should-stay-plain"

    decrypted = decrypt_sensitive_options(encrypted, PROJECT_SENSITIVE_KEYS)
    assert decrypted["telegram_token"] == "tok_123"
    assert decrypted["connection"] == "postgresql://user:pass@host/db"
    assert decrypted["unrelated_key"] == "should-stay-plain"


def test_encrypt_sensitive_options_with_nested_sync_sources():
    opts = {
        "sync_sources": [
            {
                "s3_secret_key": "secret123",
                "confluence_api_token": "conf-tok",
                "bucket": "my-bucket",
            }
        ]
    }
    encrypted = encrypt_sensitive_options(opts, PROJECT_SENSITIVE_KEYS)
    src = encrypted["sync_sources"][0]
    assert src["s3_secret_key"].startswith("$ENC$")
    assert src["confluence_api_token"].startswith("$ENC$")
    assert src["bucket"] == "my-bucket"

    decrypted = decrypt_sensitive_options(encrypted, PROJECT_SENSITIVE_KEYS)
    dsrc = decrypted["sync_sources"][0]
    assert dsrc["s3_secret_key"] == "secret123"
    assert dsrc["confluence_api_token"] == "conf-tok"


def test_llm_sensitive_keys_contains_expected():
    expected = {"api_key", "key", "password", "secret"}
    for k in expected:
        assert k in LLM_SENSITIVE_KEYS, f"{k} missing from LLM_SENSITIVE_KEYS"


def test_hash_api_key_consistent():
    key = "sk-test-1234567890"
    h1 = hash_api_key(key)
    h2 = hash_api_key(key)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex digest length


def test_generate_recovery_codes_count_and_uniqueness():
    codes = generate_recovery_codes(count=10)
    assert len(codes) == 10
    assert len(set(codes)) == 10, "Recovery codes should be unique"
    for code in codes:
        assert len(code) == 8
        assert code.isalnum()


def test_hash_recovery_code_consistent():
    code = "abcd1234"
    h1 = hash_recovery_code(code)
    h2 = hash_recovery_code(code)
    assert h1 == h2
    assert len(h1) == 64
