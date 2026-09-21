"""Connect historical fights to fighter profiles."""

from collections import defaultdict
from dataclasses import replace

from upset.data.models import Fight, Fighter


def link_historical_fights(
    fights: list[Fight],
    profiles: list[Fighter],
    overrides: list[dict],
) -> list[Fight]:
    """Return linked copies, rejecting missing or inconsistent matches."""

    profiles_by_id = {}
    profiles_by_name = defaultdict(list)

    for profile in profiles:
        profile_key = (profile.source, profile.source_fighter_id)

        if profile_key in profiles_by_id:
            raise ValueError(f"Duplicate profile ID: {profile_key}")

        profiles_by_id[profile_key] = profile
        profiles_by_name[(profile.source, profile.name)].append(profile)

    overrides_by_slot = {}

    for override in overrides:
        side = override["fighter_side"]

        if type(side) is not int or side not in (1, 2):
            raise ValueError("Override fighter_side must be 1 or 2.")

        key = (
            override["source"],
            override["source_bout_id"],
            side,
        )

        if key in overrides_by_slot:
            raise ValueError(f"Duplicate override: {key}")

        overrides_by_slot[key] = override

    linked_fights = []
    seen_fights = set()
    used_overrides = set()

    for fight in fights:
        fight_key = (fight.source, fight.source_bout_id)

        if fight_key in seen_fights:
            raise ValueError(f"Duplicate fight ID: {fight_key}")

        seen_fights.add(fight_key)
        participant_ids = {}

        for side in (1, 2):
            name = getattr(fight, f"fighter_{side}_name")
            candidates = profiles_by_name.get((fight.source, name), [])
            slot_key = (fight.source, fight.source_bout_id, side)
            override = overrides_by_slot.get(slot_key)

            if override is not None:
                # Overrides are reviewed exceptions for name collisions.
                if len(candidates) < 2:
                    raise ValueError(
                        f"Override no longer describes an ambiguity: {slot_key}"
                    )

                opponent = getattr(fight, f"fighter_{3 - side}_name")

                if (
                    override["fighter_name"] != name
                    or override["event_date"] != fight.event_date
                    or override["opponent_name"] != opponent
                ):
                    raise ValueError(
                        f"Override does not match fight details: {slot_key}"
                    )

                profile_id = override["source_fighter_id"]
                candidate_ids = {
                    profile.source_fighter_id for profile in candidates
                }

                if profile_id not in candidate_ids:
                    raise ValueError(
                        f"Override selects an invalid profile: {slot_key}"
                    )

                used_overrides.add(slot_key)

            elif len(candidates) == 1:
                profile_id = candidates[0].source_fighter_id

            else:
                raise ValueError(
                    f"Unresolved participant: {slot_key}, "
                    f"name={name!r}, candidates={len(candidates)}"
                )

            field = f"source_fighter_{side}_id"
            existing_id = getattr(fight, field)

            if existing_id is not None and existing_id != profile_id:
                raise ValueError(
                    f"Existing fighter ID conflicts with match: {slot_key}"
                )

            participant_ids[field] = profile_id

        if (
            participant_ids["source_fighter_1_id"]
            == participant_ids["source_fighter_2_id"]
        ):
            raise ValueError(f"Both participants have the same ID: {fight_key}")

        # Return a new Fight object; leave the original unchanged.
        linked_fights.append(replace(fight, **participant_ids))

    unused_overrides = set(overrides_by_slot) - used_overrides

    if unused_overrides:
        raise ValueError(
            f"Overrides reference fights not supplied: {sorted(unused_overrides)}"
        )

    return linked_fights