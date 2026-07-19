LOCK_MESSAGE_COUNT = 14
MAGIC_LOCK_LEVEL = 20
ATTRIBUTE_SCALE = 256

def attribute_display_from_memory(scaled_value: int) -> int:
    return round(scaled_value * 100 / ATTRIBUTE_SCALE)

def class_index_from_name(class_name, class_names) -> int | None:
    if not class_name:
        return None
    target = class_name.strip().casefold()
    for i, name in enumerate(class_names):
        if name and name.strip().casefold() == target:
            return i
    return None

def thieving_chance(lock_level: int, thieving_divisor: int, player_level: int, intelligence: int, agility: int) -> int:
    if thieving_divisor <= 0:
        raise ValueError('thieving_divisor must be > 0')
    if lock_level <= 0:
        raise ValueError('lock_level must be > 0')
    attributes_modifier = intelligence + agility
    ability = attributes_modifier // thieving_divisor * (player_level + 1) * 100 // (lock_level * 100)
    return max(0, min(100, ability))

def find_nearest_lock(player_x: int, player_z: int, locks, max_range: int=3):
    best = None
    best_d = None
    for entry in locks:
        x, y, level = (entry[0], entry[1], entry[2])
        d = abs(x - player_x) + abs(y - player_z)
        if d <= max_range and (best_d is None or d < best_d):
            best = (x, y, level)
            best_d = d
    return best

def lock_difficulty_index(lock_level: int, thieving_divisor: int, player_level: int, intelligence: int, agility: int) -> int:
    if lock_level >= MAGIC_LOCK_LEVEL:
        return LOCK_MESSAGE_COUNT - 1
    chance = thieving_chance(lock_level, thieving_divisor, player_level, intelligence, agility)
    index = chance // 5 - 6
    return max(0, min(LOCK_MESSAGE_COUNT - 2, index))
