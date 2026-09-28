from __future__ import annotations
import struct
from dataclasses import dataclass
from typing import Optional
ARTIFACT_QUEST_OFFSET = 4061
ARTIFACT_QUEST_SIZE = 19
DUNGEON_ID_BASE = 32
NO_PROVINCE = 255

@dataclass(frozen=True)
class ArtifactQuest:
    current_artifact: int
    map_dungeon_id: int
    map_province_id: int
    artifact_dungeon_id: int
    artifact_province_id: int
    flags: int
    price_or_offset: int

    def dungeon_role(self, province_id: int, location_id: int) -> Optional[str]:
        for role, prov, dungeon in (('map', self.map_province_id, self.map_dungeon_id), ('artifact', self.artifact_province_id, self.artifact_dungeon_id)):
            if prov != NO_PROVINCE and prov == province_id and (dungeon + DUNGEON_ID_BASE == location_id):
                return role
        return None

    def chest_cell(self) -> Optional[tuple[int, int]]:
        value = int(self.price_or_offset)
        if value & 1:
            return None
        return ((value & 255) // 2, value >> 8)

def parse_artifact_quest(raw: bytes) -> Optional[ArtifactQuest]:
    if raw is None or len(raw) < ARTIFACT_QUEST_SIZE:
        return None
    return ArtifactQuest(current_artifact=raw[0], map_dungeon_id=raw[5], map_province_id=raw[6], artifact_dungeon_id=raw[7], artifact_province_id=raw[8], flags=raw[9], price_or_offset=struct.unpack_from('<H', raw, 17)[0])

def read_artifact_quest(analyzer, anchor: Optional[int]) -> Optional[ArtifactQuest]:
    if analyzer is None or anchor is None:
        return None
    try:
        raw = analyzer.read_bytes(anchor + ARTIFACT_QUEST_OFFSET, ARTIFACT_QUEST_SIZE)
    except (OSError, RuntimeError, ValueError, OverflowError):
        return None
    return parse_artifact_quest(raw)
__all__ = ['ARTIFACT_QUEST_OFFSET', 'ARTIFACT_QUEST_SIZE', 'ArtifactQuest', 'parse_artifact_quest', 'read_artifact_quest']
