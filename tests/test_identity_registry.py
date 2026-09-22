import json
from pathlib import Path

import pytest

from upset.data.identity import (
    FighterIdentity,
    FighterProviderLink,
    FighterRegistry,
    add_reviewed_cito_link,
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


def _two_historical_fighters() -> FighterRegistry:
    return FighterRegistry(
        identities=(
            FighterIdentity(FIGHTER_ID_1, "Same Name"),
            FighterIdentity(FIGHTER_ID_2, "Same Name"),
        ),
        provider_links=(
            FighterProviderLink("ufcstats", "profile-a", FIGHTER_ID_1, "URL a"),
            FighterProviderLink("ufcstats", "profile-b", FIGHTER_ID_2, "URL b"),
        ),
    )


def test_reviewed_cito_link_preserves_identity_and_both_provider_ids(tmp_path: Path):
    registry = _two_historical_fighters()
    evidence = "Reviewed Cito profile and historical bout against UFCStats."

    result = add_reviewed_cito_link(
        registry,
        cito_fighter_id="cito-17",
        ufcstats_fighter_id="profile-b",
        evidence=evidence,
    )

    assert len(registry.provider_links) == 2  # Original is unchanged.
    assert result.identities == registry.identities
    assert result.provider_links[-1] == FighterProviderLink(
        "cito", "cito-17", FIGHTER_ID_2, evidence
    )
    path = tmp_path / "registry.json"
    save_fighter_registry(result, path)
    assert load_fighter_registry(path).provider_links[-1].upset_fighter_id == FIGHTER_ID_2
    assert add_reviewed_cito_link(
        result,
        cito_fighter_id="cito-17",
        ufcstats_fighter_id="profile-b",
        evidence=evidence,
    ) is result


def test_reviewed_cito_link_rejects_unknown_historical_id_and_conflicts():
    registry = _two_historical_fighters()
    with pytest.raises(ValueError, match="Unknown UFCStats fighter ID"):
        add_reviewed_cito_link(
            registry,
            cito_fighter_id="cito-17",
            ufcstats_fighter_id="missing",
            evidence="Reviewed profiles",
        )

    linked = add_reviewed_cito_link(
        registry,
        cito_fighter_id="cito-17",
        ufcstats_fighter_id="profile-a",
        evidence="Reviewed profiles",
    )
    with pytest.raises(ValueError, match="different identity"):
        add_reviewed_cito_link(
            linked,
            cito_fighter_id="cito-17",
            ufcstats_fighter_id="profile-b",
            evidence="Reviewed profiles",
        )
    with pytest.raises(ValueError, match="different evidence"):
        add_reviewed_cito_link(
            linked,
            cito_fighter_id="cito-17",
            ufcstats_fighter_id="profile-a",
            evidence="Altered evidence",
        )


@pytest.mark.parametrize("field", ["cito_fighter_id", "ufcstats_fighter_id", "evidence"])
def test_reviewed_cito_link_requires_nonempty_unpadded_fields(field):
    inputs = {
        "cito_fighter_id": "cito-17",
        "ufcstats_fighter_id": "profile-a",
        "evidence": "Reviewed profiles",
    }
    inputs[field] = " padded "
    with pytest.raises(ValueError, match="surrounding whitespace"):
        add_reviewed_cito_link(_two_historical_fighters(), **inputs)
