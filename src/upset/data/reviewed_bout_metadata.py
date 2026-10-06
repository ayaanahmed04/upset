"""Evidence-backed research metadata overlays; frozen source rows stay intact.

These two Cito rows retained division names but not their championship status.
Reviewed October 6, 2026 UTC against UFC's official UFC 328 scorecards/results.
Five scheduled/observed rounds alone never establish a title fight.
"""

TITLE_SOURCE = "https://www.ufc.com/news/ufc-328-official-scorecards-chimaev-vs-strickland-judges"

REVIEWED_TITLE_BOUTS = {
    ("cito", "70f1621080b3435c"): {
        "event_date": "2026-05-09",
        "fighter_ids": frozenset(("78da7aae-3d1c-4b1e-9ce3-e91bccccf7b6",
                                  "59b863b8-106c-40e8-93cd-270d7194ecb6")),
        "division": "Middleweight",
    },
    ("cito", "c85b530861145935"): {
        "event_date": "2026-05-09",
        "fighter_ids": frozenset(("b43fda44-3d56-40d4-bb1b-1644586119fb",
                                  "45505fe3-2b68-42cc-8a29-8c71b5280f07")),
        "division": "Flyweight",
    },
}


def reviewed_title_evidence(fight):
    entry = REVIEWED_TITLE_BOUTS.get((fight["source"], fight["source_bout_id"]))
    if entry is None:
        return None
    if (fight["event_date"] != entry["event_date"]
            or frozenset((fight["upset_fighter_1_id"], fight["upset_fighter_2_id"])) != entry["fighter_ids"]
            or fight.get("weight_class") not in (entry["division"], f"UFC {entry['division']} Title Bout")):
        raise ValueError("Reviewed title-bout metadata does not match this dated matchup.")
    return {"source_url": TITLE_SOURCE, "reviewed_at": "2026-10-06",
            "reason": "Official UFC 328 scorecards identify both championship bouts."}
