from __future__ import annotations

from typing import Literal

FindingConfidenceLike = Literal["low", "medium", "high"] | str | None
FindingProofTypeLike = (
    Literal[
        "deterministic_pattern",
        "runtime_check",
        "exploit_succeeded",
        "manual_review_recommendation",
    ]
    | str
    | None
)

IMPACT_SUMMARY_MAX_LENGTH = 110
EVIDENCE_TEXT_MAX_LENGTH = 180

_IMPACT_TEMPLATES: dict[str, str] = {
    "idor_candidate": "Users may be able to access another user's record by changing an ID.",
    "suspicious_missing_authorization": "Users may be able to act outside their intended permissions.",
    "authorization_disabled_flag": "Authorization checks may be disabled on this code path.",
    "allow_all_policy": "Authorization rules may allow access more broadly than intended.",
    "missing_signature_verification": "A forged webhook could trigger state changes without a trusted signature.",
    "signature_verification_disabled": "A forged webhook could trigger state changes without a trusted signature.",
    "missing_idempotency_review": "Repeated webhook deliveries may trigger the same state change more than once.",
    "stripe_secret_key": "This exposed secret may allow direct access to production systems.",
    "stripe_webhook_secret": "This exposed secret may allow forged webhook traffic to look trusted.",
    "aws_access_key_id": "This exposed secret may allow direct access to production systems.",
    "aws_secret_access_key": "This exposed secret may allow direct access to production systems.",
    "service_role_secret": "This exposed secret may allow direct access to production systems.",
    "db_connection_string": "This exposed secret may allow direct access to production data.",
    "generic_api_token": "This exposed secret may allow direct access to production systems.",
    "public_secret_exposure": "A client-exposed secret-like value may leak to every site visitor.",
    "service_role_in_frontend": "This client-side secret could be extracted by any site visitor.",
    "hardcoded_client_token": "This client-side token could be extracted by any site visitor.",
    "token_storage": "A browser-stored token could be stolen and reused from a compromised page.",
    "wildcard_cors_with_credentials": "An untrusted site may be able to use a victim's browser session against this app.",
    "reflective_cors_origin": "An untrusted site may be able to use a victim's browser session against this app.",
    "debug_enabled_in_production_config": "Production debug mode can leak internals that help attackers.",
    "security_headers_disabled": "Browsers may have weaker protection against script injection or clickjacking.",
    "missing_security_headers_review": "Browsers may have weaker protection against script injection or clickjacking.",
    "raw_request_parsing_without_validation": "Untrusted request data may reach business logic without validation.",
    "weak_body_type": "Untrusted request data may reach business logic without validation.",
    "missing_schema_validation_review": "Untrusted request data may reach business logic without validation.",
    "unsafe_eval": "Untrusted input may reach code execution.",
    "unsafe_exec": "Untrusted input may reach code execution.",
    "subprocess_shell_true": "Untrusted input may reach shell execution.",
    "raw_sql_string_concatenation": "Untrusted input may be able to change a database query.",
    "unsafe_yaml_load": "Untrusted data may trigger unsafe object loading or code execution.",
    "unsafe_pickle_load": "Untrusted data may trigger unsafe object loading or code execution.",
    "unsafe_html_sink": "User-controlled HTML may execute in a visitor's browser.",
    "missing_lockfile": "The build may resolve unexpected dependency code between installs.",
    "multiple_lockfiles": "Conflicting lockfiles can make production dependencies unpredictable.",
    "floating_version": "The build may resolve unexpected dependency code between installs.",
    "git_dependency": "The build may pull dependency code straight from an unreviewed source.",
    "install_script_review": "Install-time scripts may run untrusted code during setup or deploys.",
    "remote_install_script": "Install-time scripts may fetch and run remote code during setup or deploys.",
    "high_risk_dependency": "A risky dependency may expose the app or build pipeline to known issues.",
    "missing_build_script": "Broken release checks make it easier to ship unsafe changes.",
    "build_failed": "Broken release checks make it easier to ship unsafe changes.",
    "test_failed": "Broken test checks make it easier to ship unsafe changes.",
    "python_compile_failed": "Broken release checks make it easier to ship unsafe changes.",
    "missing_lint_script": "Missing lint checks make it easier to ship unsafe changes.",
    "lint_failed": "Broken lint checks make it easier to ship unsafe changes.",
    "typecheck_failed": "Broken type checks make it easier to ship unsafe changes.",
    "broken_script": "Broken quality gates make it easier to ship unsafe changes.",
    "dangerous_codegen_guidance": "These AI coding rules may push generated code toward unsafe patterns.",
    "security_bypass_guidance": "These AI coding rules may encourage generated code to skip core security checks.",
    "secret_literal_in_ai_rules": "A real-looking secret appears in an AI rule file and may spread through prompts or code.",
    "secret_handling_guidance": "These AI coding rules may encourage unsafe secret handling.",
    "hidden_instruction_pattern": "Hidden AI instructions can bypass normal review and governance.",
    "risky_guardrail_wording": "These AI coding rules set vague boundaries that can lead to unsafe changes.",
}


def clean_text(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().split())
    return normalized or None


def normalize_technical_summary(
    value: object | None,
    *,
    title: str,
    impact_summary: object | None = None,
) -> str:
    return clean_text(value) or clean_text(impact_summary) or clean_text(title) or "Finding details pending."


def clip_evidence_text(value: object | None, *, max_length: int = EVIDENCE_TEXT_MAX_LENGTH) -> str | None:
    cleaned = clean_text(value)
    if cleaned is None:
        return None
    if len(cleaned) <= max_length:
        return cleaned

    clipped = cleaned[: max_length - 3].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return f"{clipped}..."


def build_impact_summary(
    value: object | None,
    *,
    title: str,
    technical_summary: str | None,
    check_name: str | None = None,
    rule_id: str | None = None,
    confidence: FindingConfidenceLike = None,
    proof_type: FindingProofTypeLike = None,
) -> str:
    explicit = clean_text(value)
    if explicit is not None:
        return _clip_sentence(explicit)

    template = _template_for_check(check_name, rule_id)
    if template is not None:
        return _clip_sentence(template)

    keyword_template = _template_for_keywords(title=title, technical_summary=technical_summary)
    if keyword_template is not None:
        return _clip_sentence(keyword_template)

    fallback = _first_sentence(technical_summary) or clean_text(title) or "Security impact needs review."
    if _should_soften(confidence=confidence, proof_type=proof_type):
        fallback = _soften_sentence(fallback)
    return _clip_sentence(fallback)


def _template_for_check(check_name: str | None, rule_id: str | None) -> str | None:
    for raw_key in (check_name, rule_id):
        key = clean_text(raw_key)
        if key is None:
            continue
        template = _IMPACT_TEMPLATES.get(key.lower())
        if template is not None:
            return template
    return None


def _template_for_keywords(*, title: str, technical_summary: str | None) -> str | None:
    haystack = " ".join(
        part for part in (clean_text(title), clean_text(technical_summary)) if part is not None
    ).lower()

    if "webhook" in haystack and "signature" in haystack:
        return "A forged webhook could trigger state changes without a trusted signature."
    if "idor" in haystack or ("ownership" in haystack and "route" in haystack):
        return "Users may be able to access another user's record by changing an ID."
    if any(token in haystack for token in ("service role", "secret", "api key", "access key")):
        return "This exposed secret may allow direct access to production systems."
    if any(token in haystack for token in ("client token", "frontend", "browser", "site visitor")):
        return "This client-side token could be extracted by any site visitor."
    if "cors" in haystack:
        return "An untrusted site may be able to use a victim's browser session against this app."
    if any(token in haystack for token in ("dangerouslysetinnerhtml", "innerhtml", "xss", "unsafe html")):
        return "User-controlled HTML may execute in a visitor's browser."
    if any(token in haystack for token in ("eval", "exec", "shell=true", "shell = true")):
        return "Untrusted input may reach code or shell execution."
    if "sql" in haystack:
        return "Untrusted input may be able to change a database query."
    if any(token in haystack for token in ("dependency", "install script", "lockfile", "package")):
        return "The build may pull or run untrusted code from the dependency chain."
    if any(token in haystack for token in ("build", "lint", "typecheck", "compile")):
        return "Broken quality gates make it easier to ship unsafe changes."
    return None


def _first_sentence(value: str | None) -> str | None:
    cleaned = clean_text(value)
    if cleaned is None:
        return None
    for separator in (". ", "! ", "? "):
        if separator in cleaned:
            head = cleaned.split(separator, 1)[0].strip()
            if head:
                return head if head.endswith((".", "!", "?")) else f"{head}."
    return cleaned


def _should_soften(*, confidence: FindingConfidenceLike, proof_type: FindingProofTypeLike) -> bool:
    normalized_confidence = clean_text(confidence)
    normalized_proof = clean_text(proof_type)
    return normalized_confidence == "low" or normalized_proof == "manual_review_recommendation"


def _soften_sentence(value: str) -> str:
    lowered = value.lower()
    if lowered.startswith(("this ", "these ", "a ", "an ", "untrusted ", "users ", "browsers ")):
        return value
    return f"This may mean {value[0].lower()}{value[1:]}" if len(value) > 1 else "This may be risky."


def _clip_sentence(value: str, *, max_length: int = IMPACT_SUMMARY_MAX_LENGTH) -> str:
    cleaned = clean_text(value) or "Security impact needs review."
    if len(cleaned) <= max_length:
        return cleaned

    clipped = cleaned[: max_length - 3].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return f"{clipped}..."
