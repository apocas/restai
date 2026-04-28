def moderate_content(text: str, policy: str = "default", **kwargs) -> str:
    """Check text for PII, blocklist terms, and high-risk patterns.

    Use this **before sending sensitive text out** (email, SMS, WhatsApp,
    webhook) or **before quoting user input back**. Returns a structured
    string the agent can parse:

    ``OK: no issues found``
    ``FLAGGED: <reason>; <reason>\\nSANITIZED: <text with PII redacted>``

    Policy is per-project. Two knobs on ``ProjectOptions``:

    * ``moderation_blocklist`` — comma-separated terms (case-insensitive
      substring match). Agent configures these in Integrations tab.
    * ``moderation_redact_pii`` — bool, default ``true``. When true, PII
      matches are replaced with ``[REDACTED:<type>]`` in ``SANITIZED``.

    Different from ``guard_output`` (which runs a separate guard
    *project* for the whole response): this is an agent-callable
    mid-flow check so the agent can decide what to do next (retry,
    rephrase, abort). Also works without a guard project configured.

    Args:
        text (str): The text to check.
        policy (str): Policy profile name. Currently only "default" is
            implemented — accepted for future extension.
    """
    import json
    import re

    if not text:
        return "OK: empty input"

    brain = kwargs.get("_brain")
    project_id = kwargs.get("_project_id")

    # Load project options for blocklist + PII toggle. We degrade
    # gracefully when project context is missing — the tool still works
    # with default policies.
    blocklist: list[str] = []
    redact_pii = True
    if brain and project_id is not None:
        try:
            from restai.database import open_db_wrapper
            db = open_db_wrapper()
            try:
                proj = db.get_project_by_id(int(project_id))
                if proj and proj.options:
                    try:
                        opts = json.loads(proj.options)
                    except Exception:
                        opts = {}
                    raw = (opts.get("moderation_blocklist") or "").strip()
                    if raw:
                        blocklist = [
                            t.strip() for t in raw.replace(";", ",").split(",")
                            if t.strip()
                        ]
                    # Default true, explicit false opts out.
                    redact_pii = opts.get("moderation_redact_pii") is not False
            finally:
                db.db.close()
        except Exception:
            # Never fail the tool on a DB hiccup — moderation is
            # advisory, and raising an error here would mean the agent
            # proceeds without checking, which is worse than best-effort.
            pass

    reasons: list[str] = []
    sanitized = text

    # PII patterns. Kept conservative: only matches that almost
    # certainly identify PII, so false positives are minimal.
    # US/UK/generic credit card (with Luhn-ish spacing), email, phone,
    # US SSN, IPv4. Unicode-aware but not exhaustive — document clearly
    # that this is "best effort" not compliance-grade.
    _PATTERNS = [
        # 13-19 digit card number with optional spaces/dashes every 4.
        ("credit_card", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
        ("email",       re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
        # E.164 or common international-ish phone: + then 8-15 digits,
        # with optional spaces/dashes/parens.
        ("phone",       re.compile(r"\+?\d[\d\s().-]{7,14}\d")),
        ("us_ssn",      re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
        ("ipv4",        re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
        # OpenAI-style API key shape. Also flags Slack bot tokens, AWS
        # access keys, GitHub tokens via their telltale prefixes.
        ("api_key",     re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,})\b")),
    ]

    pii_hits: dict[str, int] = {}
    for label, rx in _PATTERNS:
        # Special-case phone: the credit-card regex is a superset. Only
        # flag phone if credit_card didn't already cover the same span
        # — otherwise every card number would also show up as a phone.
        if label == "phone" and "credit_card" in pii_hits:
            continue
        matches = list(rx.finditer(text))
        if matches:
            pii_hits[label] = len(matches)
            if redact_pii:
                sanitized = rx.sub(f"[REDACTED:{label}]", sanitized)

    if pii_hits:
        reasons.append(
            "pii_detected:" + ",".join(f"{k}={v}" for k, v in sorted(pii_hits.items()))
        )

    # Blocklist: case-insensitive substring match. Short and literal is
    # intentional — regex in admin-configurable fields is a footgun.
    if blocklist:
        lower = text.lower()
        hits = [term for term in blocklist if term.lower() in lower]
        if hits:
            reasons.append("blocklist:" + ",".join(hits[:10]))
            if redact_pii:
                for term in hits:
                    sanitized = re.sub(
                        re.escape(term), "[REDACTED:blocked]", sanitized, flags=re.IGNORECASE
                    )

    # Simple injection-probe signals. Not exhaustive — this is a smoke
    # test, not a full prompt-injection defense.
    _INJECTION_PATTERNS = [
        r"ignore (?:all )?previous",
        r"disregard (?:the |all )?instructions",
        r"system prompt",
        r"you are now",
    ]
    for pat in _INJECTION_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            reasons.append(f"possible_injection:{pat}")
            break  # one signal is enough

    if not reasons:
        return "OK: no issues found"

    parts = ["FLAGGED: " + "; ".join(reasons)]
    if redact_pii and sanitized != text:
        parts.append(f"SANITIZED: {sanitized}")
    return "\n".join(parts)
