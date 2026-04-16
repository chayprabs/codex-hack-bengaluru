from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from support import ensure_api_path

ensure_api_path()

from app.models import Finding  # noqa: E402
from app.services import PatchVerificationRequest, patch_verification_service  # noqa: E402


class PatchVerifierTests(unittest.TestCase):
    def test_secret_patch_verifies_env_reference_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "app" / "settings.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                "\n".join(
                    [
                        "import os",
                        'STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")',
                    ]
                ),
                encoding="utf-8",
            )

            result = patch_verification_service.verify_patch(
                PatchVerificationRequest(
                    repo_root=root,
                    finding=self._finding(
                        file_path="app/settings.py",
                        check_name="stripe_secret_key",
                        title="Hardcoded Stripe secret key",
                        impact_summary="A runtime secret was committed directly in source.",
                        suggested_patch="Move the secret to an environment variable reference.",
                    ),
                )
            )

            self.assertEqual(result.status, "verified")
            self.assertEqual(result.checks[0].rule_id, "secret_env_reference")
            self.assertEqual(result.checks[0].status, "passed")

    def test_webhook_patch_verifies_signature_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "app" / "routes" / "webhooks.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                "\n".join(
                    [
                        "import stripe",
                        "from fastapi import HTTPException, Request",
                        "",
                        "async def handle_webhook(request: Request):",
                        '    signature = request.headers.get("stripe-signature")',
                        '    secret = "ignored-at-runtime"',
                        "    try:",
                        "        stripe.Webhook.construct_event(await request.body(), signature, secret)",
                        "    except ValueError:",
                        '        raise HTTPException(status_code=400, detail="Invalid signature")',
                    ]
                ),
                encoding="utf-8",
            )

            result = patch_verification_service.verify_patch(
                PatchVerificationRequest(
                    repo_root=root,
                    finding=self._finding(
                        file_path="app/routes/webhooks.py",
                        check_name="missing_signature_verification",
                        title="Webhook accepts unsigned events",
                        impact_summary="Unsigned callbacks can mutate billing state.",
                        suggested_patch="Add a signature check before processing the callback payload.",
                    ),
                )
            )

            self.assertEqual(result.status, "verified")
            self.assertEqual(result.checks[0].rule_id, "webhook_signature_guard")
            self.assertEqual(result.checks[0].status, "passed")

    def test_ownership_patch_can_be_partially_verified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "app" / "routes" / "exports.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                "\n".join(
                    [
                        "def export_invoice(repo, workspace_id, invoice_id):",
                        '    return repo.invoices.find_first(where={"id": invoice_id, "workspace_id": workspace_id})',
                    ]
                ),
                encoding="utf-8",
            )

            result = patch_verification_service.verify_patch(
                PatchVerificationRequest(
                    repo_root=root,
                    finding=self._finding(
                        file_path="app/routes/exports.py",
                        check_name="idor_candidate",
                        title="Invoice export trusts workspace_id from the query string",
                        impact_summary="The export path may return data outside the active tenant.",
                        suggested_patch="Add a workspace ownership filter and generate a regression test stub for this route.",
                    ),
                )
            )

            self.assertEqual(result.status, "partially_verified")
            self.assertEqual(
                {check.rule_id: check.status for check in result.checks},
                {
                    "ownership_filter": "passed",
                    "regression_note_or_test": "failed",
                },
            )

    def test_config_patch_verifies_tightened_cors_and_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "app" / "core" / "middleware.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                "\n".join(
                    [
                        'app.add_middleware(CORSMiddleware, allow_origins=["https://app.example.com"], allow_credentials=False)',
                        'response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"',
                    ]
                ),
                encoding="utf-8",
            )

            result = patch_verification_service.verify_patch(
                PatchVerificationRequest(
                    repo_root=root,
                    finding=self._finding(
                        file_path="app/core/middleware.py",
                        check_name="wildcard_cors_with_credentials",
                        title="Wildcard CORS with credentials",
                        impact_summary="Browsers can attach credentials to overly broad origins.",
                        suggested_patch="Restrict allowed origins and restore security headers.",
                    ),
                )
            )

            self.assertEqual(result.status, "verified")
            self.assertEqual(result.checks[0].rule_id, "config_tightening")
            self.assertEqual(result.checks[0].status, "passed")

    def test_unsafe_function_patch_can_fail_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "app" / "runtime.py"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                "\n".join(
                    [
                        "def parse_value(user_input):",
                        "    return eval(user_input)",
                    ]
                ),
                encoding="utf-8",
            )

            result = patch_verification_service.verify_patch(
                PatchVerificationRequest(
                    repo_root=root,
                    finding=self._finding(
                        file_path="app/runtime.py",
                        check_name="unsafe_eval",
                        title="Unsafe eval on request data",
                        impact_summary="User input reaches eval without validation.",
                        suggested_patch="Replace eval with json.loads and a safer parser.",
                    ),
                )
            )

            self.assertEqual(result.status, "could_not_verify")
            self.assertEqual(result.checks[0].rule_id, "unsafe_function_replacement")
            self.assertEqual(result.checks[0].status, "failed")

    @staticmethod
    def _finding(
        *,
        file_path: str,
        check_name: str,
        title: str,
        impact_summary: str,
        suggested_patch: str,
    ) -> Finding:
        return Finding(
            severity="high",
            title=title,
            check_name=check_name,
            files=[file_path],
            line_hints=["12"],
            impact_summary=impact_summary,
            evidence_snippet="test fixture",
            confidence="high",
            proof_type="deterministic_pattern",
            suggested_patch=suggested_patch,
        )


if __name__ == "__main__":
    unittest.main()
