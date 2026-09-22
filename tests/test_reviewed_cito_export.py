"""Real registry preservation and failure cases for reviewed provider links."""

import json
from pathlib import Path

import pytest

from upset.data.export_reviewed_cito_links import export_reviewed_cito_links
from upset.data.identity import (
    FighterIdentity,
    FighterProviderLink,
    FighterRegistry,
    load_fighter_registry,
    save_fighter_registry,
)

FIGHTER_ID = "00000000-0000-4000-8000-000000000001"


def _inputs(tmp_path: Path) -> tuple[Path, Path]:
    registry_path = tmp_path / "fighter_registry.json"
    review_path = tmp_path / "cito_fighter_reviews.json"
    save_fighter_registry(
        FighterRegistry(
            identities=(FighterIdentity(FIGHTER_ID, "Fighter"),),
            provider_links=(
                FighterProviderLink(
                    "ufcstats", "ufcstats-1", FIGHTER_ID, "Profile URL"
                ),
            ),
        ),
        registry_path,
    )
    review_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "provider": "cito",
                "reviews": [
                    {
                        "cito_fighter_id": "cito-1",
                        "ufcstats_fighter_id": "ufcstats-1",
                        "evidence": "Reviewed both profiles and a shared bout.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return review_path, registry_path


def test_export_preserves_permanent_id_and_is_repeatable(tmp_path: Path):
    review_path, registry_path = _inputs(tmp_path)
    assert export_reviewed_cito_links(review_path, registry_path) == (1, 2, 1)

    after = load_fighter_registry(registry_path)
    assert after.identities == (FighterIdentity(FIGHTER_ID, "Fighter"),)
    assert after.provider_links[-1] == FighterProviderLink(
        "ufcstats", "ufcstats-1", FIGHTER_ID, "Profile URL"
    )
    assert any(
        link.provider == "cito"
        and link.provider_fighter_id == "cito-1"
        and link.upset_fighter_id == FIGHTER_ID
        for link in after.provider_links
    )
    first_bytes = registry_path.read_bytes()
    assert export_reviewed_cito_links(review_path, registry_path) == (1, 2, 1)
    assert registry_path.read_bytes() == first_bytes


@pytest.mark.parametrize(
    "problem", ["missing", "duplicate", "wrong_provider", "bad_json"]
)
def test_invalid_reviews_leave_registry_untouched(tmp_path: Path, problem: str):
    review_path, registry_path = _inputs(tmp_path)
    original_bytes = registry_path.read_bytes()
    if problem == "bad_json":
        review_path.write_text("{broken", encoding="utf-8")
    else:
        document = json.loads(review_path.read_text(encoding="utf-8"))
        if problem == "missing":
            document["reviews"][0]["ufcstats_fighter_id"] = "unknown"
        elif problem == "duplicate":
            document["reviews"].append(document["reviews"][0])
        else:
            document["provider"] = "ufcstats"
        review_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError):
        export_reviewed_cito_links(review_path, registry_path)
    assert registry_path.read_bytes() == original_bytes


def test_cannot_use_registry_file_as_review_document(tmp_path: Path):
    _, registry_path = _inputs(tmp_path)
    with pytest.raises(ValueError, match="must not overwrite"):
        export_reviewed_cito_links(registry_path, registry_path)
