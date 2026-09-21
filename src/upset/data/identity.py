"""UPSET-owned fighter identities and links to provider identifiers."""

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import UUID, uuid4

FIGHTER_REGISTRY_SCHEMA_VERSION = 1

def _require_nonempty(value: str, field_name: str) -> None:
    """Require a nonempty string without surrounding whitespace."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a nonempty string")

    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def validate_upset_fighter_id(upset_fighter_id: str) -> None:
    """Validate UPSET's canonical lowercase UUID4 representation."""
    _require_nonempty(upset_fighter_id, "upset_fighter_id")

    try:
        parsed_id = UUID(upset_fighter_id)
    except ValueError as error:
        raise ValueError("upset_fighter_id must be a valid UUID") from error

    if parsed_id.version != 4:
        raise ValueError("upset_fighter_id must be a UUID4")

    if str(parsed_id) != upset_fighter_id:
        raise ValueError(
            "upset_fighter_id must use the canonical lowercase UUID format"
        )


@dataclass(frozen=True)
class FighterIdentity:
    """A lasting UPSET identity with an editable display label."""

    upset_fighter_id: str
    display_name: str

    def __post_init__(self) -> None:
        validate_upset_fighter_id(self.upset_fighter_id)
        _require_nonempty(self.display_name, "display_name")


@dataclass(frozen=True)
class FighterProviderLink:
    """An evidence-backed link from a provider profile to an identity."""

    provider: str
    provider_fighter_id: str
    upset_fighter_id: str
    evidence: str

    def __post_init__(self) -> None:
        _require_nonempty(self.provider, "provider")
        _require_nonempty(self.provider_fighter_id, "provider_fighter_id")
        validate_upset_fighter_id(self.upset_fighter_id)
        _require_nonempty(self.evidence, "evidence")

        if self.provider != self.provider.lower():
            raise ValueError("provider must use a lowercase canonical code")


def new_fighter_identity(display_name: str) -> FighterIdentity:
    """Create a fighter identity with a new permanent UPSET UUID."""
    return FighterIdentity(
        upset_fighter_id=str(uuid4()),
        display_name=display_name,
    )


def validate_fighter_registry(
    identities: Iterable[FighterIdentity],
    provider_links: Iterable[FighterProviderLink],
) -> None:
    """Validate uniqueness and references across a fighter registry."""
    identity_ids: set[str] = set()

    for identity in identities:
        if identity.upset_fighter_id in identity_ids:
            raise ValueError(
                f"duplicate UPSET fighter ID: {identity.upset_fighter_id}"
            )

        identity_ids.add(identity.upset_fighter_id)

    provider_keys: set[tuple[str, str]] = set()

    for link in provider_links:
        provider_key = (link.provider, link.provider_fighter_id)

        if provider_key in provider_keys:
            raise ValueError(
                "provider fighter profile is linked more than once: "
                f"{link.provider}:{link.provider_fighter_id}"
            )

        if link.upset_fighter_id not in identity_ids:
            raise ValueError(
                "provider link references an unknown UPSET fighter ID: "
                f"{link.upset_fighter_id}"
            )

        provider_keys.add(provider_key)

@dataclass(frozen=True)
class FighterRegistry:
    """The saved collection of identities and provider links."""

    identities: tuple[FighterIdentity, ...]
    provider_links: tuple[FighterProviderLink, ...]

    def __post_init__(self) -> None:
        validate_fighter_registry(self.identities, self.provider_links)


def _registry_payload(registry: FighterRegistry) -> dict[str, object]:
    """Convert a registry into a consistently ordered JSON-ready dictionary."""
    identities = sorted(
        registry.identities,
        key=lambda identity: identity.upset_fighter_id,
    )
    provider_links = sorted(
        registry.provider_links,
        key=lambda link: (link.provider, link.provider_fighter_id),
    )

    return {
        "schema_version": FIGHTER_REGISTRY_SCHEMA_VERSION,
        "identities": [asdict(identity) for identity in identities],
        "provider_links": [asdict(link) for link in provider_links],
    }


def load_fighter_registry(path: str | Path) -> FighterRegistry:
    """Load and validate a fighter registry from JSON."""
    registry_path = Path(path)

    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("fighter registry must contain valid JSON") from error

    if not isinstance(payload, dict):
        raise TypeError("fighter registry must be a JSON object")

    expected_keys = {"schema_version", "identities", "provider_links"}
    if set(payload) != expected_keys:
        raise ValueError(
            "fighter registry must contain exactly: "
            "schema_version, identities, provider_links"
        )

    schema_version = payload["schema_version"]
    if (
        type(schema_version) is not int
        or schema_version != FIGHTER_REGISTRY_SCHEMA_VERSION
    ):
        raise ValueError(
            f"unsupported fighter registry schema version: {schema_version}"
        )

    identity_records = payload["identities"]
    provider_link_records = payload["provider_links"]

    if not isinstance(identity_records, list):
        raise TypeError("fighter registry identities must be a list")

    if not isinstance(provider_link_records, list):
        raise TypeError("fighter registry provider_links must be a list")

    try:
        identities = tuple(
            FighterIdentity(**record) for record in identity_records
        )
        provider_links = tuple(
            FighterProviderLink(**record) for record in provider_link_records
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid fighter registry record: {error}") from error

    return FighterRegistry(
        identities=identities,
        provider_links=provider_links,
    )


def save_fighter_registry(
    registry: FighterRegistry,
    path: str | Path,
    *,
    overwrite: bool = False,
) -> None:
    """Safely save and verify a fighter registry as JSON."""
    output_path = Path(path)

    if output_path.suffix != ".json":
        raise ValueError("fighter registry path must end in .json")

    if output_path.exists() and not overwrite:
        raise FileExistsError(f"fighter registry already exists: {output_path}")

    validate_fighter_registry(
        registry.identities,
        registry.provider_links,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.name}.tmp")
    payload = _registry_payload(registry)

    try:
        temporary_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        verified_registry = load_fighter_registry(temporary_path)

        if _registry_payload(verified_registry) != payload:
            raise RuntimeError("fighter registry read-back verification failed")

        temporary_path.replace(output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise