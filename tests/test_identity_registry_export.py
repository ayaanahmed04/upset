import json
from collections.abc import Callable
from pathlib import Path

import pytest

from upset.data.export_identity_registry import (
    build_fighter_registry,
    export_fighter_registry,
)
from upset.data.identity import (
    FighterIdentity,
    load_fighter_registry,
)

FIGHTER_ID_1 = "00000000-0000-4000-8000-000000000001"
FIGHTER_ID_2 = "00000000-0000-4000-8000-000000000002"


def _profile(
    provider_fighter_id: str,
    name: str,
    *,
    source: str = "kaggle_ufc_1994_2026",
) -> dict[str, object]:
    return {
        "source": source,
        "source_fighter_id": provider_fighter_id,
        "name": name,
    }


def _identity_factory(
    fighter_ids: list[str],
) -> Callable[[str], FighterIdentity]:
    remaining_ids = iter(fighter_ids)

    def create_identity(display_name: str) -> FighterIdentity:
        return FighterIdentity(
            upset_fighter_id=next(remaining_ids),
            display_name=display_name,
        )

    return create_identity


def test_build_creates_identity_and_provider_link() -> None:
    summary = build_fighter_registry(
        [_profile("ufcstats-1", "Jon Jones")],
        identity_factory=_identity_factory([FIGHTER_ID_1]),
    )

    assert summary.input_profiles == 1
    assert summary.reused_profiles == 0
    assert summary.created_identities == 1
    assert summary.registry.identities == (
        FighterIdentity(FIGHTER_ID_1, "Jon Jones"),
    )

    link = summary.registry.provider_links[0]

    assert link.provider == "ufcstats"
    assert link.provider_fighter_id == "ufcstats-1"
    assert link.upset_fighter_id == FIGHTER_ID_1


def test_build_rejects_duplicate_provider_id() -> None:
    profiles = [
        _profile("duplicate-id", "First Fighter"),
        _profile("duplicate-id", "Second Fighter"),
    ]

    with pytest.raises(ValueError, match="duplicate UFCStats fighter ID"):
        build_fighter_registry(
            profiles,
            identity_factory=_identity_factory([FIGHTER_ID_1]),
        )


def test_build_rejects_unexpected_source() -> None:
    profiles = [
        _profile(
            "fighter-1",
            "Jon Jones",
            source="unexpected_source",
        )
    ]

    with pytest.raises(ValueError, match="unexpected fighter profile source"):
        build_fighter_registry(profiles)


def test_rebuild_preserves_existing_identity_and_display_name() -> None:
    first_summary = build_fighter_registry(
        [_profile("fighter-1", "Jon Jones")],
        identity_factory=_identity_factory([FIGHTER_ID_1]),
    )

    second_summary = build_fighter_registry(
        [_profile("fighter-1", "Jonathan Jones")],
        first_summary.registry,
        identity_factory=_identity_factory([]),
    )

    assert second_summary.reused_profiles == 1
    assert second_summary.created_identities == 0
    assert second_summary.registry.identities == (
        FighterIdentity(FIGHTER_ID_1, "Jon Jones"),
    )


def test_rebuild_adds_only_new_profile() -> None:
    first_summary = build_fighter_registry(
        [_profile("fighter-1", "Jon Jones")],
        identity_factory=_identity_factory([FIGHTER_ID_1]),
    )

    second_summary = build_fighter_registry(
        [
            _profile("fighter-1", "Jon Jones"),
            _profile("fighter-2", "Daniel Cormier"),
        ],
        first_summary.registry,
        identity_factory=_identity_factory([FIGHTER_ID_2]),
    )

    assert second_summary.reused_profiles == 1
    assert second_summary.created_identities == 1
    assert len(second_summary.registry.identities) == 2


def test_export_saves_loadable_registry(tmp_path: Path) -> None:
    profile_path = tmp_path / "fighters.jsonl"
    registry_path = tmp_path / "fighter_registry.json"

    profile_path.write_text(
        json.dumps(_profile("fighter-1", "Jon Jones")) + "\n",
        encoding="utf-8",
    )

    export_fighter_registry(
        profile_path,
        registry_path,
        identity_factory=_identity_factory([FIGHTER_ID_1]),
    )

    registry = load_fighter_registry(registry_path)

    assert registry.identities == (
        FighterIdentity(FIGHTER_ID_1, "Jon Jones"),
    )
    assert registry.provider_links[0].provider_fighter_id == "fighter-1"