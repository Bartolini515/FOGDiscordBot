"""Pure experience and level calculations."""

MAXEXP = 55100
MAXLVL = 100
MAXEXPGAIN = 25
MINEXPGAIN = 10


def calculate_experience(level: int) -> int:
    """Return the experience threshold for a level."""

    return int(5 * (level**2) + (50 * level) + 100)


def calculate_level(experience: int) -> int:
    """Return the level represented by an experience total."""

    return int((-50 + (20 * experience + 500) ** 0.5) / 10)


def check_level_up(current_experience: int, new_experience: int) -> bool:
    """Return whether a new total crosses a level boundary."""

    return calculate_level(new_experience) > calculate_level(current_experience)


def next_experience(current_experience: int, gained_experience: int, maximum: int = MAXEXP) -> int:
    """Add experience while preserving the configured maximum cap."""

    return min(current_experience + gained_experience, maximum)
