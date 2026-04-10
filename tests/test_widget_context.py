"""Tests for widget context verification and system prompt injection."""
import json
import time

import jwt
import pytest

from restai.utils.widget_context import (
    verify_widget_context,
    apply_widget_context,
)

SECRET = "test-secret-key-for-widget-context"


def _make_token(claims, secret=SECRET, **kwargs):
    return jwt.encode(claims, secret, algorithm="HS256", **kwargs)


# ---------- verify_widget_context ----------


class TestVerifyWidgetContext:

    def test_valid_token(self):
        token = _make_token({"sub": "user-1", "name": "Alice", "exp": int(time.time()) + 3600})
        result = verify_widget_context(token, SECRET)
        assert result["sub"] == "user-1"
        assert result["name"] == "Alice"
        assert "exp" not in result
        assert "iat" not in result

    def test_expired_token_rejected(self):
        token = _make_token({"sub": "user-1", "exp": int(time.time()) - 10})
        with pytest.raises(ValueError, match="expired"):
            verify_widget_context(token, SECRET)

    def test_wrong_secret_rejected(self):
        token = _make_token({"sub": "user-1", "exp": int(time.time()) + 3600})
        with pytest.raises(ValueError, match="Invalid"):
            verify_widget_context(token, "wrong-secret")

    def test_missing_token_rejected(self):
        with pytest.raises(ValueError, match="Missing"):
            verify_widget_context("", SECRET)

    def test_missing_secret_rejected(self):
        token = _make_token({"sub": "user-1", "exp": int(time.time()) + 3600})
        with pytest.raises(ValueError, match="Missing"):
            verify_widget_context(token, "")

    def test_jwt_reserved_claims_stripped(self):
        claims = {
            "sub": "user-1",
            "name": "Alice",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "nbf": int(time.time()),
            "iss": "test",
            "jti": "abc123",
        }
        token = _make_token(claims)
        result = verify_widget_context(token, SECRET)
        assert "sub" in result
        assert "name" in result
        for key in ("exp", "iat", "nbf", "iss", "jti"):
            assert key not in result

    def test_dangerous_keys_stripped(self):
        claims = {
            "sub": "user-1",
            "system": "override system prompt",
            "prompt": "evil prompt",
            "instructions": "do bad things",
            "name": "Alice",
            "exp": int(time.time()) + 3600,
        }
        token = _make_token(claims)
        result = verify_widget_context(token, SECRET)
        assert result["name"] == "Alice"
        assert "system" not in result
        assert "prompt" not in result
        assert "instructions" not in result

    def test_excessive_ttl_rejected(self):
        # Token with 48h TTL should be rejected (max is 24h)
        now = int(time.time())
        token = _make_token({"sub": "user-1", "iat": now, "exp": now + 48 * 3600})
        with pytest.raises(ValueError, match="TTL"):
            verify_widget_context(token, SECRET)

    def test_oversized_payload_rejected(self):
        big_value = "x" * 5000
        token = _make_token({"sub": "user-1", "data": big_value, "exp": int(time.time()) + 3600})
        with pytest.raises(ValueError, match="too large"):
            verify_widget_context(token, SECRET)

    def test_nested_claims(self):
        claims = {
            "sub": "user-1",
            "meta": {"plan": "enterprise", "department": "eng"},
            "exp": int(time.time()) + 3600,
        }
        token = _make_token(claims)
        result = verify_widget_context(token, SECRET)
        assert result["meta"]["plan"] == "enterprise"


# ---------- apply_widget_context ----------


class TestApplyWidgetContext:

    def test_template_substitution(self):
        prompt = "Hello {{context.name}}, you are a {{context.role}}."
        context = {"name": "Alice", "role": "admin"}
        result = apply_widget_context(prompt, context, prepend_block=False)
        assert result == "Hello Alice, you are a admin."

    def test_missing_key_resolves_to_empty(self):
        prompt = "Hello {{context.name}}, tier: {{context.tier}}."
        context = {"name": "Bob"}
        result = apply_widget_context(prompt, context, prepend_block=False)
        assert result == "Hello Bob, tier: ."

    def test_dotted_key_for_nested_dict(self):
        prompt = "Plan: {{context.meta.plan}}"
        context = {"meta": {"plan": "enterprise"}}
        result = apply_widget_context(prompt, context, prepend_block=False)
        assert result == "Plan: enterprise"

    def test_no_recursive_expansion(self):
        # If a claim value itself looks like a template, it should NOT be expanded
        prompt = "Name: {{context.name}}"
        context = {"name": "{{context.evil}}", "evil": "INJECTED"}
        result = apply_widget_context(prompt, context, prepend_block=False)
        assert result == "Name: {{context.evil}}"
        assert "INJECTED" not in result

    def test_prepend_block(self):
        prompt = "You are a helpful assistant."
        context = {"name": "Alice", "role": "admin"}
        result = apply_widget_context(prompt, context, prepend_block=True)
        assert result.startswith("[User Context]")
        assert "name: Alice" in result
        assert "role: admin" in result
        assert "[/User Context]" in result
        assert result.endswith("You are a helpful assistant.")

    def test_prepend_block_with_nested(self):
        prompt = "System prompt."
        context = {"name": "Alice", "meta": {"plan": "pro", "region": "eu"}}
        result = apply_widget_context(prompt, context, prepend_block=True)
        assert "meta.plan: pro" in result
        assert "meta.region: eu" in result

    def test_no_prepend_when_disabled(self):
        prompt = "Hello {{context.name}}."
        context = {"name": "Alice"}
        result = apply_widget_context(prompt, context, prepend_block=False)
        assert "[User Context]" not in result
        assert result == "Hello Alice."

    def test_empty_context_is_noop(self):
        prompt = "Hello {{context.name}}."
        result = apply_widget_context(prompt, {}, prepend_block=True)
        assert result == "Hello {{context.name}}."

    def test_none_context_is_noop(self):
        prompt = "Hello."
        result = apply_widget_context(prompt, None, prepend_block=True)
        assert result == "Hello."

    def test_empty_prompt_with_context(self):
        result = apply_widget_context("", {"name": "Alice"}, prepend_block=True)
        assert "name: Alice" in result

    def test_both_prepend_and_template(self):
        prompt = "Assist {{context.name}} with their {{context.role}} tasks."
        context = {"name": "Bob", "role": "engineering"}
        result = apply_widget_context(prompt, context, prepend_block=True)
        assert result.startswith("[User Context]")
        assert "Assist Bob with their engineering tasks." in result
