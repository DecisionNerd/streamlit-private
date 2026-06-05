"""The ``streamlit-private.yaml`` manifest — the project's source of truth (FR-7).

The manifest records the provider selections every later command reads: version,
framework, auth provider, hosting provider. Its schema is small and flat, so we
emit and parse it by hand rather than take a YAML dependency — keeping the CLI's
``dependencies = []`` (ADR-0007). The parser is intentionally **strict**: it
accepts exactly the shape we emit and fails with a clear error otherwise, rather
than guessing at hand-edited input that a later command would misread.
"""

from __future__ import annotations

from dataclasses import dataclass

MANIFEST_NAME = "streamlit-private.yaml"
MANIFEST_VERSION = 1
FRAMEWORK = "streamlit"


class ManifestError(ValueError):
    """Raised when ``streamlit-private.yaml`` cannot be parsed into a Manifest."""


@dataclass(frozen=True)
class Manifest:
    """The parsed manifest. ``framework`` is always ``streamlit`` for now."""

    auth_provider: str
    hosting_provider: str
    version: int = MANIFEST_VERSION
    framework: str = FRAMEWORK

    def dump(self) -> str:
        """Render the canonical YAML. Deterministic key order; nested provider keys."""
        return (
            f"version: {self.version}\n"
            f"framework: {self.framework}\n"
            "auth:\n"
            f"  provider: {self.auth_provider}\n"
            "hosting:\n"
            f"  provider: {self.hosting_provider}\n"
        )


def dump(manifest: Manifest) -> str:
    return manifest.dump()


def load(text: str) -> Manifest:
    """Parse the canonical manifest shape. Strict: unknown structure → ManifestError.

    Accepts the flat top-level keys ``version`` / ``framework`` and the two
    one-level-nested tables ``auth.provider`` / ``hosting.provider``. Comments
    (``#``) and blank lines are ignored; values may be quoted.
    """
    top: dict[str, str] = {}
    nested: dict[str, dict[str, str]] = {}
    current_section: str | None = None

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        indented = line[0] in (" ", "\t")
        stripped = line.strip()
        if ":" not in stripped:
            raise ManifestError(
                f"{MANIFEST_NAME}: line {lineno}: expected 'key: value', got {raw_line!r}"
            )
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = _unquote(value.strip())

        if not indented:
            if value == "":
                # Section header like `auth:` — subsequent indented keys belong to it.
                current_section = key
                nested.setdefault(key, {})
            else:
                top[key] = value
                current_section = None
        else:
            if current_section is None:
                raise ManifestError(f"{MANIFEST_NAME}: line {lineno}: indented key with no section")
            nested[current_section][key] = value

    try:
        auth_provider = nested["auth"]["provider"]
        hosting_provider = nested["hosting"]["provider"]
    except KeyError as exc:
        raise ManifestError(
            f"{MANIFEST_NAME}: missing required key auth.provider/hosting.provider"
        ) from exc

    version_raw = top.get("version", str(MANIFEST_VERSION))
    try:
        version = int(version_raw)
    except ValueError as exc:
        raise ManifestError(
            f"{MANIFEST_NAME}: version must be an integer, got {version_raw!r}"
        ) from exc

    return Manifest(
        auth_provider=auth_provider,
        hosting_provider=hosting_provider,
        version=version,
        framework=top.get("framework", FRAMEWORK),
    )


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value
