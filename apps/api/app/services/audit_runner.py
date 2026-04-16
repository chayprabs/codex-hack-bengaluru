from ..models import AgentStatus, Audit, Finding, utc_now


class AuditRunner:
    """Placeholder audit-runner orchestration for the hackathon backend."""

    def build_initial_agents(self) -> list[AgentStatus]:
        return [
            AgentStatus(name="planner"),
            AgentStatus(name="scanner"),
            AgentStatus(name="verifier"),
        ]

    def build_demo_result(self, audit: Audit) -> Audit:
        demo_finding = Finding(
            severity="medium",
            title="Placeholder finding",
            summary="TrustLayer demo finding. Replace this once the agent pipeline is wired.",
            file_path="README.md",
            line=1,
            created_at=utc_now(),
        )
        return audit.model_copy(
            update={
                "status": "completed",
                "updated_at": utc_now(),
                "findings": [demo_finding],
                "agents": [
                    AgentStatus(name="planner", status="completed", message="Plan drafted."),
                    AgentStatus(
                        name="scanner",
                        status="completed",
                        message="Placeholder scan done.",
                    ),
                    AgentStatus(
                        name="verifier",
                        status="completed",
                        message="Placeholder review done.",
                    ),
                ],
            }
        )


audit_runner = AuditRunner()
