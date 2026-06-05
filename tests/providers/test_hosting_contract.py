"""Shared HostingProvider contract suite (FR-23).

Runs the same assertions against every provider implementation — the in-memory
fake and the (subprocess-mocked) Railway provider — proving the interface is
real and capability-shaped, not leaning on one vendor (ADR-0002).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from streamlit_private.hosting.interface import (
    DeployConfig,
    DeployResult,
    HostingProvider,
)
from tests.providers.fakes import FakeHostingProvider


@pytest.fixture(params=["fake", "railway"])
def provider(request, monkeypatch) -> HostingProvider:
    if request.param == "fake":
        return FakeHostingProvider()
    # Railway with subprocess fully mocked so the contract runs offline.
    from tests.providers._railway_mock import mocked_railway

    return mocked_railway(monkeypatch)


def _config(tmp_path: Path) -> DeployConfig:
    return DeployConfig(
        repo_root=tmp_path,
        project_name="myapp",
        env={"SP_SESSION_SECRET": "s", "CLERK_JWT_KEY": "k", "CLERK_SIGN_IN_URL": "u"},
    )


def test_deploy_returns_https_url(provider: HostingProvider, tmp_path: Path) -> None:
    result = provider.deploy(_config(tmp_path))
    assert isinstance(result, DeployResult)
    assert result.url.startswith("https://")


def test_update_returns_result(provider: HostingProvider, tmp_path: Path) -> None:
    result = provider.update(_config(tmp_path))
    assert isinstance(result, DeployResult)
    assert result.url.startswith("https://")


def test_set_env_accepts_dict(provider: HostingProvider) -> None:
    provider.set_env({"A": "1", "B": "2"})  # must not raise


def test_assign_domain_returns_https(provider: HostingProvider) -> None:
    assert provider.assign_domain(service="myapp", port=8000).startswith("https://")


def test_attach_volume_not_supported_in_v1(provider: HostingProvider) -> None:
    # Pinned: a future implementer must consciously change this contract.
    with pytest.raises(NotImplementedError):
        provider.attach_volume(mount_path="/data")


def test_provider_has_name(provider: HostingProvider) -> None:
    assert provider.name


def test_abc_enforces_all_methods() -> None:
    # A subclass missing an abstract method cannot be instantiated.
    class Incomplete(HostingProvider):
        name = "incomplete"

        def deploy(self, config):  # noqa: D401
            ...

    with pytest.raises(TypeError):
        Incomplete()  # missing update/set_env/attach_volume/assign_domain
