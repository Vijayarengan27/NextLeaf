def trait_match_score(
    preferences: dict,
    book_traits: dict,
) -> float | None:
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