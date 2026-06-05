# Releasing to PyPI

`streamlit-private` is published to PyPI via **Trusted Publishing** (OIDC) — no API token is
ever stored (ADR-0007). The release workflow (`.github/workflows/release.yml`) builds the
sdist + wheel with `uv` and publishes when a version tag (`v*`) is pushed. Two steps need a
human: a one-time PyPI registration, and cutting each release.

## One-time setup (maintainer, before the first release)

The project has never been published, so register a **pending publisher** — it creates the
project on first successful publish and converts to a normal publisher automatically.

1. Log in to <https://pypi.org> and verify your account email.
2. Open **Account settings → Publishing**: <https://pypi.org/manage/account/publishing/>
   (the project doesn't exist yet, so this is registered at the *account* level).
3. Under **Add a new pending publisher** (GitHub tab), fill in exactly:
   - **PyPI Project Name:** `streamlit-private`
   - **Owner:** `DecisionNerd`
   - **Repository name:** `streamlit-private`
   - **Workflow name:** `release.yml` (just the filename, not a path)
   - **Environment name:** `pypi` (must match `release.yml`'s `environment: name: pypi`)
4. Click **Add**.
5. *(Recommended)* In the GitHub repo, create an Environment named **`pypi`**
   (Settings → Environments) and add a **required reviewer** so each publish needs manual
   approval — a human gate before anything goes public.

> A pending publisher does **not** reserve the name until first use. Register it and publish
> promptly so no one else claims `streamlit-private` in between.

## Cutting a release

1. Bump `version` in `pyproject.toml` (and `__version__` in `src/streamlit_private/__init__.py`).
2. Ensure `main` is green (CI: lint + tests 3.11–3.13 + skills checks).
3. Tag and push:
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```
4. The **Release** workflow runs: `build` produces the artifacts, `publish` (after any
   environment approval) uploads to PyPI via OIDC.
5. Verify: `uvx streamlit-private --version` resolves the published version from PyPI.

## Notes

- **Skills** are distributed separately and need no PyPI publish: `npx skills add
  DecisionNerd/streamlit-private` pulls `SKILL.md` files straight from GitHub (ADR-0006).
- The `[gateway]` and `[admin]` extras are published as part of the same package; users opt in
  with `streamlit-private[gateway]` / `[admin]`.
- Trusted Publishing also uploads Sigstore **attestations** by default (no extra config).
