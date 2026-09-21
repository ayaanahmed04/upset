from uuid import UUID

import pytest

from upset.data.identity import (
    FighterIdentity,
    FighterProviderLink,
    new_fighter_identity,
    validate_fighter_registry,
)

FIGHTER_ID_1 = "00000000-0000-4000-8000-000000000001"
FIGHTER_ID_2 = "00000000-0000-4000-8000-000000000002"


def test_new_fighter_identity_creates_canonical_uuid4() -> None:
    identity = new_fighter_identity("Jon Jones")

    parsed_id = UUID(identity.upset_fighter_id)

    assert parsed_id.version == 4
    assert str(parsed_id) == identity.upset_fighter_id
    assert identity.display_name == "Jon Jones"


def test_two_provider_profiles_can_link_to_same_identity() -> None:
    identity = FighterIdentity(FIGHTER_ID_1, "Jon Jones")
    links = [
        FighterProviderLink(
            "ufcstats",
            "ufcstats-jon-jones",
            FIGHTER_ID_1,
            "Matched from the historical UFCStats profile.",
        ),
        FighterProviderLink(
            "cito",
            "cito-jon-jones",
            FIGHTER_ID_1,
            "Reviewed against the UFCStats profile.",
        ),
    ]

    validate_fighter_registry([identity], links)


def test_display_names_are_not_identity_keys() -> None:
    identities = [
        FighterIdentity(FIGHTER_ID_1, "Alex Silva"),
        FighterIdentity(FIGHTER_ID_2, "Alex Silva"),
    ]

    validate_fighter_registry(identities, [])


def test_identity_rejects_invalid_uuid() -> None:
    with pytest.raises(ValueError, match="valid UUID"):
        FighterIdentity("fighter-123", "Jon Jones")


def test_registry_rejects_duplicate_identity_id() -> None:
    identities = [
        FighterIdentity(FIGHTER_ID_1, "Jon Jones"),
        FighterIdentity(FIGHTER_ID_1, "Jonathan Jones"),
    ]

    with pytest.raises(ValueError, match="duplicate UPSET fighter ID"):
        validate_fighter_registry(identities, [])


def test_registry_rejects_provider_profile_conflict() -> None:
    identities = [
        FighterIdentity(FIGHTER_ID_1, "Jon Jones"),
        FighterIdentity(FIGHTER_ID_2, "Daniel Cormier"),
    ]
    links = [
        FighterProviderLink(
            "ufcstats",
            "same-provider-id",
            FIGHTER_ID_1,
            "First reviewed link.",
        ),
        FighterProviderLink(
            "ufcstats",
            "same-provider-id",
            FIGHTER_ID_2,
            "Conflicting reviewed link.",
        ),
    ]

    with pytest.raises(ValueError, match="linked more than once"):
        validate_fighter_registry(identities, links)


def test_registry_rejects_unknown_identity_reference() -> None:
    link = FighterProviderLink(
        "ufcstats",
        "ufcstats-jon-jones",
        FIGHTER_ID_1,
        "Reviewed historical profile.",
    )

    with pytest.raises(ValueError, match="unknown UPSET fighter ID"):
        validate_fighter_registry([], [link])


def test_records_reject_blank_or_noncanonical_fields() -> None:
    invalid_record_factories = [
        lambda: FighterIdentity(FIGHTER_ID_1, ""),
        lambda: FighterIdentity(FIGHTER_ID_1, " Jon Jones"),
        lambda: FighterProviderLink(
            "UFCStats",
            "provider-id",
            FIGHTER_ID_1,
            "Reviewed link.",
        ),
        lambda: FighterProviderLink(
            "ufcstats",
            "",
            FIGHTER_ID_1,
            "Reviewed link.",
        ),
        lambda: FighterProviderLink(
            "ufcstats",
            "provider-id",
            FIGHTER_ID_1,
            "",
        ),
    ]

    for create_invalid_record in invalid_record_factories:
        with pytest.raises(ValueError):
            create_invalid_record()