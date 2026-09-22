"""Apply explicitly reviewed Cito links to the permanent fighter registry."""

import json
from pathlib import Path

from upset.data.identity import (
    FighterRegistry,
    add_reviewed_cito_link,
    load_fighter_registry,
    save_fighter_registry,
)

DEFAULT_REVIEW_PATH = Path("data/mappings/cito_fighter_reviews.json")
DEFAULT_REGISTRY_PATH = Path("data/mappings/fighter_registry.json")
_REVIEW_FIELDS = {"cito_fighter_id", "ufcstats_fighter_id", "evidence"}


def apply_reviewed_cito_links(
    registry: FighterRegistry, document: object
) -> FighterRegistry:
    """Validate the complete review document before returning updated links."""
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "provider",
        "reviews",
    }:
        raise ValueError("Cito review document has unexpected fields.")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise ValueError("Unsupported Cito review schema version.")
    if document["provider"] != "cito":
        raise ValueError("Cito review provider must be 'cito'.")

    reviews = document["reviews"]
    if not isinstance(reviews, list) or not reviews:
        raise ValueError("Cito review document must contain reviewed links.")

    updated = registry
    seen_cito_ids = set()
    for row in reviews:
        if not isinstance(row, dict) or set(row) != _REVIEW_FIELDS:
            raise ValueError("Cito review entry has unexpected fields.")
        cito_id = row["cito_fighter_id"]
        if not isinstance(cito_id, str):
            raise TypeError("Cito fighter ID must be text.")
        if cito_id in seen_cito_ids:
            raise ValueError(f"Duplicate reviewed Cito fighter ID: {cito_id}")
        seen_cito_ids.add(cito_id)
        updated = add_reviewed_cito_link(updated, **row)

    return updated


def export_reviewed_cito_links(
    review_path: Path = DEFAULT_REVIEW_PATH,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
) -> tuple[int, int, int]:
    """Apply reviewed links and safely replace the verified registry."""
    if review_path.resolve() == registry_path.resolve():
        raise ValueError("Review document must not overwrite the registry.")

    original = load_fighter_registry(registry_path)
    try:
        document = json.loads(review_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("Cito review document must contain valid JSON.") from error

    updated = apply_reviewed_cito_links(original, document)
    if updated != original:
        save_fighter_registry(updated, registry_path, overwrite=True)
    cito_links = sum(link.provider == "cito" for link in updated.provider_links)
    return len(updated.identities), len(updated.provider_links), cito_links


def main() -> None:
    identities, links, cito_links = export_reviewed_cito_links()
    print(f"Permanent fighter identities: {identities}")
    print(f"Provider links: {links}")
    print(f"Reviewed Cito links: {cito_links}")
    print("Registry validation: passed")
    print(f"Saved to: {DEFAULT_REGISTRY_PATH}")


if __name__ == "__main__":
    main()
