# Testing

We test **behavior first**. Something is correct and shippable when the experiences in
[`1-EXPERIENCES.md`](1-EXPERIENCES.md) and the requirements in
[`2-REQUIREMENTS.md`](2-REQUIREMENTS.md) are demonstrably met — especially the two guarantees
the project lives or dies by: **never modify the user's app**, and **proxy Streamlit
(including WebSockets) faithfully**. Fast unit feedback guards the CLI logic; integration and
end-to-end tests prove the gateway and provider integrations actually work.

## Strategy

| Layer | What it verifies | Tools |
|---|---|---|
| Unit | Streamlit detection signals, manifest read/write, idempotency/`--force` decisions, scaffolder file planning. | `pytest` |
| Integration | Gateway authz decisions over a faked AuthProvider; reverse proxy + WebSocket upgrade against a real local Streamlit; provider implementations against mocked Clerk/Railway APIs. | `pytest`, `httpx`/`starlette` test client, `respx`/mock servers |
| End-to-end / behavior | The two-command journey (`init` → `deploy`) and the access matrix against sandbox provider accounts. | `pytest` + Clerk/Railway sandboxes |

## Behavior coverage

| Experience / Requirement | Scenario (Given/When/Then) | Test |
|---|---|---|
| Initialize a new private app / FR-1, FR-7 | Given an empty dir, When `init`, Then app+gateway+assets+manifest are created. | `tests/cli/test_init_new.py` |
| Wrap an existing app / FR-2, NFR-2 | Given a Streamlit repo, When `init`, Then infra is added and **no app file changes** (hash every pre-existing file). | `tests/cli/test_init_existing.py` |
| Streamlit detection / FR-3 | Given each signal (`pages/`, `import streamlit[ as st]`, `requirements.txt`, `pyproject.toml`), When detect, Then repo is recognized. | `tests/cli/test_detection.py` |
| Reject non-Streamlit / FR-4 | Given a non-Streamlit non-empty repo, When `init`, Then refusal message and **zero files modified**. | `tests/cli/test_init_reject.py` |
| Idempotency / FR-5 | Given an initialized repo, When `init` again, Then "already configured" message and no changes. | `tests/cli/test_idempotency.py` |
| Reconfigure / FR-6 | Given an initialized repo, When `init --force` with new providers, Then assets regenerate and **app code preserved**. | `tests/cli/test_force_reconfigure.py` |
| Deploy privately / FR-8, FR-9 | Given a manifest, When `deploy railway`, Then HostingProvider.deploy is invoked and a private URL returned. | `tests/cli/test_deploy.py` |
| Authorize by org membership / FR-11, FR-12, FR-13 | Given member/non-member/unauthenticated, When request, Then allow / request-access / sign-in respectively. | `tests/gateway/test_authorization.py` |
| Session validation / FR-14 | Given an invalid/expired session, When request, Then treated as unauthenticated. | `tests/gateway/test_session.py` |
| Identity headers / FR-15, NFR-4 | Given an allowed member, When proxied, Then `X-User-*`/`X-Organization-Id` injected; spoofed inbound headers are stripped. | `tests/gateway/test_identity_headers.py` |
| Reverse proxy paths / FR-16 | Given a running Streamlit, When requesting `/`, `static/*`, `_stcore/*`, `media/*`, Then proxied correctly. | `tests/gateway/test_proxy_spike.py`, `tests/gateway/test_real_streamlit_spike.py` |
| WebSocket upgrade / FR-17, FR-18 | Given a Streamlit session, When the `_stcore/stream` WS upgrades, Then it round-trips through the gateway (upgrade + subprotocol negotiated end-to-end). | `tests/gateway/test_real_streamlit_spike.py` |
| WebSocket re-authorization / FR-32 | Given an open WS, When the user's membership is revoked, Then the socket closes within one heartbeat interval; When the user stays valid, Then the socket is never disconnected; When heartbeats lapse, Then the socket closes fail-closed. | `tests/gateway/test_ws_revalidation.py` |
| Invite a user / FR-19 | Given an admin, When invite, Then AuthProvider.create_invitation is called; acceptance yields membership. | `tests/workflows/test_invitations.py` |
| Request & approve access / FR-20, FR-21 | Given a non-member request, When admin approves, Then AuthProvider.add_member is called (reject discards). | `tests/workflows/test_access_requests.py` |
| AuthProvider contract / FR-22 | Given the Clerk impl, When run against the shared contract suite, Then all capabilities conform. | `tests/providers/test_auth_contract.py` |
| HostingProvider contract / FR-23 | Given the Railway impl, When run against the shared contract suite, Then all capabilities conform. | `tests/providers/test_hosting_contract.py` |
| Skills are valid & discoverable / FR-26, FR-27 | Given the repo's `skills/`, When parsed, Then every `SKILL.md` has valid `name`/`description` frontmatter and is found by the `skills` CLI discovery layout. | `tests/skills/test_skill_manifests.py` |
| CLI/skills parity / FR-28, NFR-8 | Given each user-facing CLI command, When listing skills, Then a matching skill exists and references the CLI command (no forked logic). | `tests/skills/test_cli_parity.py` |
| Skills preserve guarantees / FR-29 | Given each action skill, When inspected, Then it instructs the agent not to edit app files and to honor idempotency/`--force`. | `tests/skills/test_skill_guarantees.py` |
| Agent-agnostic / FR-30 | Given the skills, When checked, Then none depend on a single agent's proprietary features (frontmatter stays within the shared Agent Skills spec). | `tests/skills/test_agent_agnostic.py` |

## Evaluation against the mission

- **Time-to-private (NFR-1)** — measure wall-clock for `init` → `deploy` on a sample existing
  app from a clean machine; "good" is minutes with no manual OAuth/proxy/Docker steps.
- **Zero app edits (NFR-2)** — automated diff/hash of every pre-existing application file
  across `init` and `init --force`; "good" is byte-for-byte unchanged.
- **Workflow completeness** — invite→accept→access and request→approve→access both complete
  against sandbox provider accounts without provider-console intervention.
- **Provider portability (NFR-5)** — the AuthProvider/HostingProvider contract suites pass
  for each implementation; switching providers is a manifest edit + regenerate.

## Running the tests

```
uv run pytest
```

(Integration/E2E suites that need live providers are marked and run with
`uv run pytest -m integration` / `-m e2e` once sandbox credentials are configured.)

## Continuous integration

CI (`.github/workflows/ci.yml`) runs on every push to `main` and every pull request: a `ruff`
lint + format check, and the test suite across Python 3.11–3.13 (the CLI's supported range,
per [ADR-0012](2-ENGINEERING/ADRs/0012-python-version-policy.md)). The **app-preservation hash
check** and **provider contract suites** are required gates before merge. End-to-end tests
(`-m e2e`) against provider sandboxes are excluded from per-commit CI and run on a schedule or
pre-release to avoid flakiness from external services.

## Test data & environments

- **Fixtures:** generated sample repos (empty, Streamlit-via-each-signal, non-Streamlit) built
  in `tmp_path`; a local Streamlit process spun up for proxy/WebSocket tests.
- **Fakes/mocks:** an in-memory `FakeAuthProvider` for gateway authz tests; mocked Clerk and
  Railway HTTP APIs for implementation tests.
- **Sandboxes:** dedicated Clerk and Railway sandbox accounts for E2E, with secrets injected
  via environment variables — never committed.
