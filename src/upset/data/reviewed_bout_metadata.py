"""Evidence-backed research metadata overlays; frozen source rows stay intact.

Title designations were reviewed October 6, 2026 UTC against official UFC evidence.
Five scheduled/observed rounds alone never establish a title fight.
"""

TITLE_SOURCE = "https://www.ufc.com/news/ufc-328-official-scorecards-chimaev-vs-strickland-judges"

REVIEWED_TITLE_BOUTS = {
    ("cito", "70f1621080b3435c"): {
        "event_date": "2026-05-09",
        "fighter_ids": frozenset(("78da7aae-3d1c-4b1e-9ce3-e91bccccf7b6",
                                  "59b863b8-106c-40e8-93cd-270d7194ecb6")),
        "division": "Middleweight",
        "source_url": TITLE_SOURCE,
        "event": "UFC 328",
    },
    ("cito", "c85b530861145935"): {
        "event_date": "2026-05-09",
        "fighter_ids": frozenset(("b43fda44-3d56-40d4-bb1b-1644586119fb",
                                  "45505fe3-2b68-42cc-8a29-8c71b5280f07")),
        "division": "Flyweight",
        "source_url": TITLE_SOURCE,
        "event": "UFC 328",
    },
    ("cito", "5727d5be8c373346"): {
        "event_date": "2026-06-14",
        "fighter_ids": frozenset(("c99a0733-de10-41a0-9e32-c0df4f214cef",
                                  "bb826765-47c1-4238-9c17-f77e59518192")),
        "division": "Heavyweight",
        "source_url": "https://www.ufc.com/news/official-weigh-results-ufc-freedom-250",
        "event": "UFC Freedom 250",
    },
    ("cito", "7208e40818401e88"): {
        "event_date": "2026-06-14",
        "fighter_ids": frozenset(("678d50b2-742c-44e4-b833-d560794ba84c",
                                  "7a1b1eb6-1471-4f85-987c-d77c340947eb")),
        "division": "Lightweight",
        "source_url": "https://www.ufc.com/news/official-weigh-results-ufc-freedom-250",
        "event": "UFC Freedom 250",
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
    return {"source_url": entry["source_url"], "reviewed_at": "2026-10-06",
            "reason": f"Official {entry['event']} evidence identifies this championship bout."}


# UFCStats uses the same Draw/NC marker for both results. These four
# ambiguous method labels were checked against the dated UFC results.
REVIEWED_RESULT_TYPES = {
    "821960adf5bfa15c": ("2023-10-21", "nc", "https://www.ufc.com/event/ufc-294"),
    "6390c8e74630473e": ("2025-10-25", "nc", "https://www.ufc.com/event/ufc-321"),
    "db8df615610f3632": ("1995-04-07", "draw", "https://www.ufc.com/event/ufc-5"),
    "640d52630f4f8a61": ("2023-04-22", "nc", "https://www.ufc.com/athlete/jared-gordon"),
}


def result_type(fight):
    result = fight.get("reviewed_result") or fight
    explicit = result.get("outcome")
    method = (result.get("result_method") or "").casefold()
    if explicit == "draw" or ("draw" in method and "nc" not in method and "/" not in method):
        return "draw", None
    if explicit in ("no_contest", "nc") or method in ("no contest", "overturned"):
        return "nc", None
    if method.startswith("decision"):
        return "draw", None
    if fight["source"] == "kaggle_ufc_1994_2026":
        reviewed = REVIEWED_RESULT_TYPES.get(fight["source_bout_id"])
        if reviewed and reviewed[0] == fight["event_date"]:
            return reviewed[1], reviewed[2]
    return "other", None
