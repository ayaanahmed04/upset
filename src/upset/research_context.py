"""Descriptive research context; never a prediction or a historical knowledge claim."""

import json


def opponent_records(db, history, window):
    """Record each opponent's accepted results strictly before that meeting.

    All bouts on the meeting date are excluded because intra-day order is unknown.
    Reviewed outcomes are used today; amendment publication dates are not known.
    Repeat opponents contribute once per meeting, with their record at that date.
    """
    selected = history[:window] if window else history
    rows = []
    for meeting in selected:
        uid = meeting["opponent_id"]
        record = {"wins": 0, "losses": 0, "other": 0}
        for (payload,) in db.execute(
            "SELECT payload FROM fights WHERE (fighter_1=? OR fighter_2=?) AND event_date<?",
            (uid, uid, meeting["date"]),
        ):
            fight = json.loads(payload)
            side = 1 if fight["upset_fighter_1_id"] == uid else 2
            winner = (fight.get("reviewed_result") or fight)["winner_name"]
            result = "other" if winner is None else (
                "wins" if winner == fight[f"fighter_{side}_name"] else "losses")
            record[result] += 1
        decisive = record["wins"] + record["losses"]
        win_fraction = record["wins"] / decisive if decisive else None
        rows.append({"fight_id": meeting["fight_id"], "date": meeting["date"],
                     "opponent_id": uid, "opponent": meeting["opponent"],
                     **record, "win_fraction": win_fraction})
    eligible = [r for r in rows if r["win_fraction"] is not None]
    wins = sum(r["wins"] for r in rows)
    losses = sum(r["losses"] for r in rows)
    return {
        "bouts": len(rows), "opponents_with_decisive_history": len(eligible),
        "opponents_without_decisive_history": len(rows) - len(eligible),
        "mean_opponent_win_fraction": (
            sum(r["win_fraction"] for r in eligible) / len(eligible) if eligible else None),
        "pooled_wins": wins, "pooled_losses": losses,
        "pooled_other_results": sum(r["other"] for r in rows),
        "pooled_opponent_win_fraction": wins / (wins + losses) if wins + losses else None,
        "meetings": rows,
        "basis": "accepted UFC results before each meeting, using currently reviewed outcomes",
    }


def control_shares(timed):
    """Paired control shares on one common, validated exposure denominator.

    The residual is uncredited control time, not measured distance time.
    Missing, negative, or overlapping control totals are excluded, never clamped.
    """
    eligible = []
    missing = invalid = 0
    for row in timed:
        own = row["own"]["control_seconds"]
        opposing = row["opponent_stats"]["control_seconds"]
        duration = row["own"]["fight_duration_seconds"]
        if own is None or opposing is None:
            missing += 1
        elif own < 0 or opposing < 0 or own + opposing > duration:
            invalid += 1
        else:
            eligible.append(row)
    seconds = sum(r["own"]["fight_duration_seconds"] for r in eligible)
    own = sum(r["own"]["control_seconds"] for r in eligible)
    opposing = sum(r["opponent_stats"]["control_seconds"] for r in eligible)
    return {
        "timed_bouts": len(timed), "observed_bouts": len(eligible),
        "missing_control_bouts": missing, "invalid_control_bouts": invalid,
        "observed_seconds": seconds,
        "own_control_seconds": own, "opponent_control_seconds": opposing,
        "in_control_fraction": own / seconds if seconds else None,
        "controlled_fraction": opposing / seconds if seconds else None,
        "neither_credited_fraction": (seconds - own - opposing) / seconds if seconds else None,
    }
