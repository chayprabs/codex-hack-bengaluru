from __future__ import annotations

from pydantic import BaseModel, Field

from .types import AgentFinding


class SpecialistCheckDefinition(BaseModel):
    id: str
    summary: str


class PatchSuggestionShape(BaseModel):
    strategy_examples: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)


class SpecialistDefinition(BaseModel):
    agent_name: str
    display_name: str
    inputs_from_repo_mapper: list[str] = Field(default_factory=list)
    files_of_interest: list[str] = Field(default_factory=list)
    checks: list[SpecialistCheckDefinition] = Field(default_factory=list)
    evidence_returns: list[str] = Field(default_factory=list)
    patch_suggestion_shape: PatchSuggestionShape


PATCH_SUGGESTION_FIELDS = [
    "strategy",
    "summary",
    "changes[].file_path",
    "changes[].action",
    "changes[].summary",
    "changes[].snippet",
]


SPECIALIST_ROSTER: list[SpecialistDefinition] = [
    SpecialistDefinition(
        agent_name="secrets",
        display_name="Secrets / Credential Agent",
        inputs_from_repo_mapper=["env", "auth", "config", "webhooks"],
        files_of_interest=[
            ".env*",
            "auth config files",
            "webhook handlers",
            "runtime config and deployment manifests",
        ],
        checks=[
            SpecialistCheckDefinition(id="stripe_secret_key", summary="Detect hardcoded Stripe secret keys."),
            SpecialistCheckDefinition(id="stripe_webhook_secret", summary="Detect hardcoded webhook signing secrets."),
            SpecialistCheckDefinition(id="aws_access_key_id", summary="Detect committed AWS access key identifiers."),
            SpecialistCheckDefinition(id="aws_secret_access_key", summary="Detect committed AWS secret access keys."),
            SpecialistCheckDefinition(id="service_role_secret", summary="Detect committed admin or service-role secrets."),
            SpecialistCheckDefinition(id="db_connection_string", summary="Detect inline database URLs with credentials."),
            SpecialistCheckDefinition(id="generic_api_token", summary="Detect generic secret-like literal assignments."),
        ],
        evidence_returns=[
            "Redacted code or config excerpt",
            "File path and line range",
            "Secret kind and detector id",
        ],
        patch_suggestion_shape=PatchSuggestionShape(
            strategy_examples=["replace_literal", "reduce_exposure"],
            fields=PATCH_SUGGESTION_FIELDS,
        ),
    ),
    SpecialistDefinition(
        agent_name="auth",
        display_name="Auth / Session Agent",
        inputs_from_repo_mapper=["auth", "routes", "env", "config", "middleware"],
        files_of_interest=[
            "auth handlers",
            "session or cookie config",
            "login and callback routes",
            "auth middleware",
        ],
        checks=[
            SpecialistCheckDefinition(id="auth_disabled_flag", summary="Detect source-level auth bypass flags."),
            SpecialistCheckDefinition(id="insecure_auth_default", summary="Detect weak default auth or session secrets."),
            SpecialistCheckDefinition(id="jwt_verification_bypass", summary="Detect JWT verification bypasses."),
            SpecialistCheckDefinition(id="insecure_session_cookie", summary="Detect insecure session cookie settings."),
            SpecialistCheckDefinition(id="suspicious_unprotected_route", summary="Review sensitive routes without obvious auth guards."),
        ],
        evidence_returns=[
            "Matched auth-setting excerpt",
            "Route or middleware locator",
            "Confidence level for absence-based coverage checks",
        ],
        patch_suggestion_shape=PatchSuggestionShape(
            strategy_examples=["tighten_config", "add_guard"],
            fields=PATCH_SUGGESTION_FIELDS,
        ),
    ),
    SpecialistDefinition(
        agent_name="authz",
        display_name="Authz / IDOR Agent",
        inputs_from_repo_mapper=["auth", "routes", "database", "validation"],
        files_of_interest=[
            "permission or policy helpers",
            "member, team, billing, or admin routes",
            "database lookups near object-id routes",
        ],
        checks=[
            SpecialistCheckDefinition(id="authorization_disabled_flag", summary="Detect source-level authorization bypass flags."),
            SpecialistCheckDefinition(id="allow_all_policy", summary="Detect allow-all policy helpers."),
            SpecialistCheckDefinition(id="suspicious_missing_authorization", summary="Review sensitive routes without explicit authz markers."),
            SpecialistCheckDefinition(id="idor_candidate", summary="Review object-id routes that look up records without ownership scoping."),
        ],
        evidence_returns=[
            "Matched policy excerpt",
            "Sensitive route locator",
            "Object-id and lookup evidence for IDOR review",
        ],
        patch_suggestion_shape=PatchSuggestionShape(
            strategy_examples=["add_guard", "add_validation"],
            fields=PATCH_SUGGESTION_FIELDS,
        ),
    ),
    SpecialistDefinition(
        agent_name="webhook",
        display_name="Webhook Agent",
        inputs_from_repo_mapper=["webhooks", "routes", "auth", "config", "env"],
        files_of_interest=[
            "webhook or callback routes",
            "provider-specific config",
            "signature verification helpers",
        ],
        checks=[
            SpecialistCheckDefinition(id="signature_verification_disabled", summary="Detect webhook signature bypass flags."),
            SpecialistCheckDefinition(id="missing_signature_verification", summary="Review provider handlers without clear signature verification."),
            SpecialistCheckDefinition(id="missing_idempotency_review", summary="Review handlers without duplicate-delivery protection markers."),
        ],
        evidence_returns=[
            "Provider-specific handler excerpt",
            "Verification or idempotency marker evidence",
            "Confidence level for absence-based checks",
        ],
        patch_suggestion_shape=PatchSuggestionShape(
            strategy_examples=["add_guard", "tighten_config"],
            fields=PATCH_SUGGESTION_FIELDS,
        ),
    ),
    SpecialistDefinition(
        agent_name="dependency",
        display_name="Dependency / Supply-Chain Agent",
        inputs_from_repo_mapper=["manifests", "lockfiles", "config"],
        files_of_interest=[
            "package.json",
            "pyproject.toml",
            "requirements*.txt",
            "lockfiles",
        ],
        checks=[
            SpecialistCheckDefinition(id="missing_lockfile", summary="Detect missing lockfiles."),
            SpecialistCheckDefinition(id="multiple_lockfiles", summary="Detect conflicting lockfiles."),
            SpecialistCheckDefinition(id="floating_version", summary="Detect fully floating dependency versions."),
            SpecialistCheckDefinition(id="git_dependency", summary="Detect git, URL, or editable dependency sources."),
            SpecialistCheckDefinition(id="install_script_review", summary="Review install lifecycle scripts."),
            SpecialistCheckDefinition(id="remote_install_script", summary="Detect lifecycle scripts that fetch remote code."),
            SpecialistCheckDefinition(id="high_risk_dependency", summary="Detect curated stale or historically risky dependency packages."),
            SpecialistCheckDefinition(id="invalid_manifest", summary="Detect invalid dependency manifests."),
        ],
        evidence_returns=[
            "Manifest excerpt or parse failure",
            "Dependency name and version/source",
            "Lifecycle script excerpt",
        ],
        patch_suggestion_shape=PatchSuggestionShape(
            strategy_examples=["pin_dependency", "tighten_config", "manual_review"],
            fields=PATCH_SUGGESTION_FIELDS,
        ),
    ),
    SpecialistDefinition(
        agent_name="config_headers_cors",
        display_name="Config / Headers / CORS Agent",
        inputs_from_repo_mapper=["config", "middleware", "env", "routes"],
        files_of_interest=[
            "middleware files",
            "framework config",
            "CORS setup",
            "header-setting utilities",
        ],
        checks=[
            SpecialistCheckDefinition(id="wildcard_cors_with_credentials", summary="Detect wildcard CORS origins paired with credentials."),
            SpecialistCheckDefinition(id="reflective_cors_origin", summary="Detect reflective or overly broad CORS origin config."),
            SpecialistCheckDefinition(id="debug_enabled_in_production_config", summary="Detect debug or development mode enabled in production-facing config."),
            SpecialistCheckDefinition(id="security_headers_disabled", summary="Detect explicitly disabled security headers."),
            SpecialistCheckDefinition(id="missing_security_headers_review", summary="Review apps without obvious header hardening markers."),
        ],
        evidence_returns=[
            "Config or middleware excerpt",
            "Header or CORS setting evidence",
            "Confidence level for missing-header reviews",
        ],
        patch_suggestion_shape=PatchSuggestionShape(
            strategy_examples=["tighten_config", "add_guard"],
            fields=PATCH_SUGGESTION_FIELDS,
        ),
    ),
    SpecialistDefinition(
        agent_name="input_validation",
        display_name="Input Validation Agent",
        inputs_from_repo_mapper=["validation", "routes", "auth", "database"],
        files_of_interest=[
            "request handlers",
            "schema or validator files",
            "DTOs and serializers",
            "database writes sourced from request data",
        ],
        checks=[
            SpecialistCheckDefinition(id="raw_request_parsing_without_validation", summary="Review request parsing without obvious schema validation."),
            SpecialistCheckDefinition(id="weak_body_type", summary="Detect `dict` or `Any` payloads on route handlers."),
            SpecialistCheckDefinition(id="missing_schema_validation_review", summary="Review body, params, or query usage without obvious validation markers."),
            SpecialistCheckDefinition(id="unsafe_eval", summary="Detect backend `eval(...)` usage."),
            SpecialistCheckDefinition(id="unsafe_exec", summary="Detect backend `exec(...)` or exec-style process helpers."),
            SpecialistCheckDefinition(id="subprocess_shell_true", summary="Detect subprocess calls that enable `shell=True`."),
            SpecialistCheckDefinition(id="raw_sql_string_concatenation", summary="Detect raw SQL string interpolation instead of parameter binding."),
            SpecialistCheckDefinition(id="unsafe_yaml_load", summary="Detect `yaml.load(...)` or `yaml.unsafe_load(...)` on backend code paths."),
            SpecialistCheckDefinition(id="unsafe_pickle_load", summary="Detect `pickle.loads(...)` or similar unsafe deserialization helpers."),
        ],
        evidence_returns=[
            "Route excerpt showing request parsing",
            "Validation-marker absence or schema evidence",
            "Exact sink line for eval, exec, shell, SQL, or deserialization hazards",
            "Line-level handler locator",
        ],
        patch_suggestion_shape=PatchSuggestionShape(
            strategy_examples=["add_validation", "add_guard"],
            fields=PATCH_SUGGESTION_FIELDS,
        ),
    ),
    SpecialistDefinition(
        agent_name="frontend_runtime",
        display_name="Frontend Runtime / XSS Agent",
        inputs_from_repo_mapper=["frontend", "config", "auth", "env", "manifests"],
        files_of_interest=[
            "client components",
            "frontend runtime config",
            "browser auth storage code",
            "HTML rendering sinks",
        ],
        checks=[
            SpecialistCheckDefinition(id="public_secret_exposure", summary="Detect secret-like public env names."),
            SpecialistCheckDefinition(id="service_role_in_frontend", summary="Detect service-role secrets referenced from browser code."),
            SpecialistCheckDefinition(id="hardcoded_client_token", summary="Detect hardcoded tokens, bearer values, or API keys in frontend source."),
            SpecialistCheckDefinition(id="token_storage", summary="Detect auth state stored in browser storage."),
            SpecialistCheckDefinition(id="unsafe_html_sink", summary="Review direct HTML injection or unsafe HTML rendering sinks."),
            SpecialistCheckDefinition(id="unsafe_eval", summary="Detect eval-like runtime execution in frontend code."),
        ],
        evidence_returns=[
            "Client-side code excerpt",
            "Env-name or sink evidence",
            "Confidence level for XSS review findings",
        ],
        patch_suggestion_shape=PatchSuggestionShape(
            strategy_examples=["reduce_exposure", "add_guard", "manual_review"],
            fields=PATCH_SUGGESTION_FIELDS,
        ),
    ),
    SpecialistDefinition(
        agent_name="build_type_lint",
        display_name="Build / Type / Lint Agent",
        inputs_from_repo_mapper=["manifests", "lockfiles", "config", "routes", "validation"],
        files_of_interest=[
            "project roots with package.json or pyproject.toml",
            "lint and typecheck config",
            "build and test scripts",
        ],
        checks=[
            SpecialistCheckDefinition(id="missing_package_manager_metadata", summary="Detect missing package manager metadata."),
            SpecialistCheckDefinition(id="missing_build_script", summary="Detect buildable apps without build scripts."),
            SpecialistCheckDefinition(id="build_failed", summary="Detect failing scoped build commands."),
            SpecialistCheckDefinition(id="test_failed", summary="Detect failing scoped test commands."),
            SpecialistCheckDefinition(id="python_compile_failed", summary="Detect failing Python compile checks."),
            SpecialistCheckDefinition(id="missing_env_example", summary="Detect project roots that use env configuration but lack a checked-in example env template."),
            SpecialistCheckDefinition(id="missing_lint_script", summary="Detect lintable projects without a lint script."),
            SpecialistCheckDefinition(id="missing_typescript_dependency", summary="Detect tsconfig without TypeScript support."),
            SpecialistCheckDefinition(id="lint_failed", summary="Detect failing lint commands."),
            SpecialistCheckDefinition(id="typecheck_failed", summary="Detect failing typecheck commands."),
            SpecialistCheckDefinition(id="broken_script", summary="Detect malformed or missing command chains."),
            SpecialistCheckDefinition(id="invalid_manifest", summary="Detect invalid build or lint manifests."),
        ],
        evidence_returns=[
            "Command label and exit summary",
            "Manifest parse error or script excerpt",
            "Scoped project root that failed verification",
        ],
        patch_suggestion_shape=PatchSuggestionShape(
            strategy_examples=["repair_build", "tighten_config", "manual_review"],
            fields=PATCH_SUGGESTION_FIELDS,
        ),
    ),
]


def specialist_roster() -> list[SpecialistDefinition]:
    return [item.model_copy(deep=True) for item in SPECIALIST_ROSTER]


def specialist_definition(agent_name: str) -> SpecialistDefinition | None:
    for item in SPECIALIST_ROSTER:
        if item.agent_name == agent_name:
            return item.model_copy(deep=True)
    return None


def shared_finding_schema() -> dict[str, object]:
    return AgentFinding.model_json_schema()
