"""Rank progression decisions."""


def should_promote_to_rank(all_time_missions: int, max_missions: int, next_required_missions: int) -> bool:
    """Return whether attendance reaches a non-terminal next-rank threshold."""

    return all_time_missions < max_missions and all_time_missions >= next_required_missions
