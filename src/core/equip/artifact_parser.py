from .solver import Candidate


def normalize_pools(
    pools: dict[str, list[Candidate]],
    required_slots: list[str],
    use_empty_placeholder: bool = True,
) -> dict[str, list[Candidate]]:
    normalized: dict[str, list[Candidate]] = {}
    for slot in required_slots:
        items = pools.get(slot, [])
        if not items and use_empty_placeholder:
            items = [Candidate(slot=slot, name="empty", score=0.0, set_name="empty")]
        normalized[slot] = items
    return normalized


def apply_avoid_characters(
    pools: dict[str, list[Candidate]],
    avoid_characters: list[str] | None = None,
) -> dict[str, list[Candidate]]:
    # Current Candidate model doesn't carry character ownership; hook kept for strict API.
    _ = avoid_characters
    return pools
