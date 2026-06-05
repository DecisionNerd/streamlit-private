"""An in-memory HostingProvider for tests — records calls, returns a canned URL.

Used by the shared contract suite and by the deploy CLI tests so neither touches
a real host. Its `attach_volume` mirrors the Railway v1 semantics (raises
NotImplementedError) so it conforms to the same contract.
"""

from __future__ import annotations

from streamlit_private.hosting.interface import (
    DeployConfig,
    DeployResult,
    HostingProvider,
)


class FakeHostingProvider(HostingProvider):
    name = "fake"

    def __init__(self) -> None:
        self.deployed: list[DeployConfig] = []
        self.env: dict[str, str] = {}
        self.domains: list[tuple[str | None, int]] = []
        self.preflight_calls = 0

    def preflight(self) -> None:
        self.preflight_calls += 1

    def deploy(self, config: DeployConfig) -> DeployResult:
        self.deployed.append(config)
        self.set_env(config.env)
        url = self.assign_domain(service=config.project_name, port=config.gateway_port)
        return DeployResult(url=url, service_id=config.project_name, environment="production")

    def update(self, config: DeployConfig) -> DeployResult:
        return self.deploy(config)

    def set_env(self, env: dict[str, str], *, service: str | None = None) -> None:
        self.env.update(env)

    def attach_volume(
        self, *, mount_path: str, name: str | None = None, service: str | None = None
    ) -> None:
        raise NotImplementedError("fake provider does not support volumes")

    def assign_domain(self, *, service: str | None = None, port: int = 8000) -> str:
        self.domains.append((service, port))
        return f"https://{service or 'app'}.up.railway.app"
