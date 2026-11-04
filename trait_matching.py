
import json


def trait_match_score(
    preferences: dict,
    book_traits: dict,
) -> float | None:
    """
    Return a 0-1 match score, or None if no traits were requested.

    Each preference:
        {"target": 0.9, "importance": 1.0}

    Importance weights determine which requested traits matter most.
    """
    weighted_error = 0.0
    total_weight = 0.0

    for trait, pref in preferences.items():
        target = pref.get("target")
        importance = float(pref.get("importance", 0.0))

        if target is None or importance <= 0:
            continue

        book_value = book_traits.get(trait)

        if book_value is None:
            continue

        target = float(target)
        book_value = float(book_value)

        if not 0 <= target <= 1 or not 0 <= book_value <= 1:
            continue

        weighted_error += importance * abs(target - book_value)
        total_weight += importance

    if total_weight == 0:
        return None

    return 1.0 - weighted_error / total_weight


def parse_book_traits(traits_json: str | dict) -> dict:
    """Accept either the JSON stored in SQLite or an existing dictionary."""
    if isinstance(traits_json, str):
        return json.loads(traits_json)
    return traits_json
