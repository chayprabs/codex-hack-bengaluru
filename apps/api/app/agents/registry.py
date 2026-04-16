from collections.abc import Iterable, Iterator

from .base import BaseAgent


class AgentRegistryError(ValueError):
    """Raised when agent registration or lookup fails."""


class AgentRegistry:
    def __init__(self, agents: Iterable[BaseAgent] | None = None) -> None:
        self._agents: dict[str, BaseAgent] = {}
        if agents is not None:
            self.register_many(agents)

    def register(self, agent: BaseAgent) -> BaseAgent:
        try:
            name = agent.agent_name
        except ValueError as exc:
            raise AgentRegistryError(str(exc)) from exc
        if name in self._agents:
            raise AgentRegistryError(f"Agent '{name}' is already registered.")

        self._agents[name] = agent
        return agent

    def register_many(self, agents: Iterable[BaseAgent]) -> None:
        for agent in agents:
            self.register(agent)

    def get(self, name: str) -> BaseAgent:
        agent = self._agents.get(name)
        if agent is None:
            raise AgentRegistryError(f"Agent '{name}' is not registered.")
        return agent

    def maybe_get(self, name: str) -> BaseAgent | None:
        return self._agents.get(name)

    def list(self) -> list[BaseAgent]:
        return list(self._agents.values())

    def names(self) -> list[str]:
        return list(self._agents.keys())

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._agents

    def __iter__(self) -> Iterator[BaseAgent]:
        return iter(self._agents.values())

    def __len__(self) -> int:
        return len(self._agents)


agent_registry = AgentRegistry()
