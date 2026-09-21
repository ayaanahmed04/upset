import json
from pathlib import Path

import pytest

from upset.data.identity import (
    FighterIdentity,
    FighterProviderLink,
    FighterRegistry,
    load_fighter_registry,
    save_fighter_registry,
)

FIGHTER_ID_1 = "00000000-0000-4000-8000-000000000001"
FIGHTER_ID_2 = "00000000-0000-4000-8000-000000000002"


def test_registry_round_trip_uses_consistent_order(tmp_path: Path) -> None:
    registry = FighterRegistry(
        identities=(
            FighterIdentity(FIGHTER_ID_2, "Daniel Cormier"),
            FighterIdentity(FIGHTER_ID_1, "Jon Jones"),
        ),
        provider_links=(
            FighterProviderLink(
                "ufcstats",
                "fighter-2",
                FIGHTER_ID_2,
                "Reviewed historical profile.",
            ),
            FighterProviderLink(
                "cito",
                "fighter-1",
                FIGHTER_ID_1,
                "Reviewed provider match.",
            ),
        ),
    )
    output_path = tmp_path / "fighter_registry.json"

    save_fighter_registry(registry, output_path)
    loaded_registry = load_fighter_registry(output_path)

    assert [identity.upset_fighter_id for identity in loaded_registry.identities] == [
        FIGHTER_ID_1,
        FIGHTER_ID_2,
    ]
    assert [
        (link.provider, link.provider_fighter_id)
        for link in loaded_registry.provider_links
    ] == [
        ("cito", "fighter-1"),
        ("ufcstats", "fighter-2"),
    ]


def test_save_refuses_to_replace_existing_registry(tmp_path: Path) -> None:
    registry = FighterRegistry(
        identities=(FighterIdentity(FIGHTER_ID_1, "Jon Jones"),),
        provider_links=(),
    )
    output_path = tmp_path / "fighter_registry.json"

    save_fighter_registry(registry, output_path)

    with pytest.raises(FileExistsError, match="already exists"):
        save_fighter_registry(registry, output_path)


def test_save_can_explicitly_replace_registry(tmp_path: Path) -> None:
    first_registry = FighterRegistry(
        identities=(FighterIdentity(FIGHTER_ID_1, "Jon Jones"),),
        provider_links=(),
    )
    updated_registry = FighterRegistry(
        identities=(FighterIdentity(FIGHTER_ID_1, "Jonathan Jones"),),
        provider_links=(),
    )
    output_path = tmp_path / "fighter_registry.json"

    save_fighter_registry(first_registry, output_path)
    save_fighter_registry(updated_registry, output_path, overwrite=True)

    loaded_registry = load_fighter_registry(output_path)

    assert loaded_registry.identities[0].display_name == "Jonathan Jones"
    assert loaded_registry.identities[0].upset_fighter_id == FIGHTER_ID_1


def test_load_rejects_unknown_schema_version(tmp_path: Path) -> None:
    output_path = tmp_path / "fighter_registry.json"
    output_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "identities": [],
                "provider_links": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported"):
        load_fighter_registry(output_path)


def test_load_rejects_link_to_unknown_identity(tmp_path: Path) -> None:
    output_path = tmp_path / "fighter_registry.json"
    output_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "identities": [],
                "provider_links": [
                    {
                        "provider": "ufcstats",
                        "provider_fighter_id": "fighter-1",
                        "upset_fighter_id": FIGHTER_ID_1,
                        "evidence": "Reviewed historical profile.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown UPSET fighter ID"):
        load_fighter_registry(output_path)


def test_load_rejects_unexpected_top_level_fields(tmp_path: Path) -> None:
    output_path = tmp_path / "fighter_registry.json"
    output_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "identities": [],
                "provider_links": [],
                "unexpected": True,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must contain exactly"):
        load_fighter_registry(output_path)