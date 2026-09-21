"""Build the permanent UPSET fighter identity registry."""

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from upset.data.identity import (
    FighterIdentity,
    FighterProviderLink,
    FighterRegistry,
    load_fighter_registry,
    new_fighter_identity,
    save_fighter_registry,
)

DEFAULT_PROFILE_PATH = Path(
    "data/processed/kaggle_ufc_1994_2026/fighters.jsonl"
)
DEFAULT_REGISTRY_PATH = Path("data/mappings/fighter_registry.json")

HISTORICAL_SOURCE = "kaggle_ufc_1994_2026"
HISTORICAL_PROVIDER = "ufcstats"
HISTORICAL_EVIDENCE = (
    "Imported from the normalized historical UFCStats-derived fighter profile."
)

IdentityFactory = Callable[[str], FighterIdentity]


@dataclass(frozen=True)
class RegistryBuildSummary:
    """The completed registry and counts from one build."""

    registry: FighterRegistry
    input_profiles: int
    reused_profiles: int
    created_identities: int


def _required_text(
    record: Mapping[str, object],
    field_name: str,
) -> str:
    """Read a required, trimmed string from a fighter profile."""
    value = record.get(field_name)

    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")

    if not value or value != value.strip():
        raise ValueError(
            f"{field_name} must be nonempty without surrounding whitespace"
        )

    return value


def read_fighter_profiles(
    path: str | Path,
) -> list[dict[str, object]]:
    """Read normalized fighter profiles from JSONL."""
    profile_path = Path(path)
    records: list[dict[str, object]] = []

    with profile_path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                raise ValueError(
                    f"blank line in fighter profile export at line {line_number}"
                )

            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    "invalid JSON in fighter profile export at "
                    f"line {line_number}"
                ) from error

            if not isinstance(record, dict):
                raise TypeError(
                    "fighter profile export records must be JSON objects"
                )

            records.append(record)

    return records


def build_fighter_registry(
    profiles: Iterable[Mapping[str, object]],
    existing_registry: FighterRegistry | None = None,
    *,
    identity_factory: IdentityFactory = new_fighter_identity,
) -> RegistryBuildSummary:
    """Create identities for new UFCStats profiles and preserve existing ones."""
    registry = existing_registry

    if registry is None:
        registry = FighterRegistry(identities=(), provider_links=())

    identities = list(registry.identities)
    provider_links = list(registry.provider_links)

    identity_ids = {
        identity.upset_fighter_id for identity in registry.identities
    }
    links_by_provider_key = {
        (link.provider, link.provider_fighter_id): link
        for link in registry.provider_links
    }

    seen_input_ids: set[str] = set()
    input_profiles = 0
    reused_profiles = 0
    created_identities = 0

    for profile in profiles:
        input_profiles += 1

        source = _required_text(profile, "source")
        if source != HISTORICAL_SOURCE:
            raise ValueError(f"unexpected fighter profile source: {source}")

        provider_fighter_id = _required_text(
            profile,
            "source_fighter_id",
        )
        display_name = _required_text(profile, "name")

        if provider_fighter_id in seen_input_ids:
            raise ValueError(
                "duplicate UFCStats fighter ID in profile export: "
                f"{provider_fighter_id}"
            )

        seen_input_ids.add(provider_fighter_id)
        provider_key = (HISTORICAL_PROVIDER, provider_fighter_id)

        if provider_key in links_by_provider_key:
            reused_profiles += 1
            continue

        identity = identity_factory(display_name)

        if not isinstance(identity, FighterIdentity):
            raise TypeError(
                "identity_factory must return a FighterIdentity"
            )

        if identity.upset_fighter_id in identity_ids:
            raise ValueError(
                "identity factory produced a duplicate UPSET fighter ID: "
                f"{identity.upset_fighter_id}"
            )

        link = FighterProviderLink(
            provider=HISTORICAL_PROVIDER,
            provider_fighter_id=provider_fighter_id,
            upset_fighter_id=identity.upset_fighter_id,
            evidence=HISTORICAL_EVIDENCE,
        )

        identities.append(identity)
        provider_links.append(link)
        identity_ids.add(identity.upset_fighter_id)
        links_by_provider_key[provider_key] = link
        created_identities += 1

    completed_registry = FighterRegistry(
        identities=tuple(identities),
        provider_links=tuple(provider_links),
    )

    return RegistryBuildSummary(
        registry=completed_registry,
        input_profiles=input_profiles,
        reused_profiles=reused_profiles,
        created_identities=created_identities,
    )


def export_fighter_registry(
    profile_path: str | Path = DEFAULT_PROFILE_PATH,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
    *,
    identity_factory: IdentityFactory = new_fighter_identity,
) -> RegistryBuildSummary:
    """Build and safely save the UPSET fighter identity registry."""
    output_path = Path(registry_path)

    if output_path.exists():
        existing_registry = load_fighter_registry(output_path)
    else:
        existing_registry = FighterRegistry(
            identities=(),
            provider_links=(),
        )

    profiles = read_fighter_profiles(profile_path)
    summary = build_fighter_registry(
        profiles,
        existing_registry,
        identity_factory=identity_factory,
    )

    save_fighter_registry(
        summary.registry,
        output_path,
        overwrite=output_path.exists(),
    )

    return summary


def main() -> None:
    """Export the historical fighter identity registry."""
    summary = export_fighter_registry()

    print(f"Input fighter profiles: {summary.input_profiles}")
    print(f"Existing identities reused: {summary.reused_profiles}")
    print(f"New identities created: {summary.created_identities}")
    print(f"Total identities: {len(summary.registry.identities)}")
    print(f"Total provider links: {len(summary.registry.provider_links)}")
    print(f"Saved to: {DEFAULT_REGISTRY_PATH}")


if __name__ == "__main__":
    main()