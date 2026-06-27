from __future__ import annotations
from typing import Dict, Optional
from .facility_node import FacilityNode, FacilityView

class ConversationNode(FacilityNode):

    def classify_view(self, w, **signals) -> FacilityView:
        return FacilityView(reason=f'seam:{self.name}')

    def render(self, w, *, view, **ctx):
        return None

class NpcChatNode(ConversationNode):
    name = 'npc_chat'

class NpcMessageNode(ConversationNode):
    name = 'npc_message'

class NpcInterruptNode(ConversationNode):
    name = 'npc_interrupt'
_CONV_REGISTRY: Dict[str, ConversationNode] = {}

def register_conversation_node(node: ConversationNode) -> None:
    _CONV_REGISTRY[node.name] = node

def get_conversation_node(name: str) -> Optional[ConversationNode]:
    return _CONV_REGISTRY.get(name or '')

def registered_conversation_names() -> list[str]:
    return sorted(_CONV_REGISTRY.keys())
NPC_CHAT_NODE = NpcChatNode()
NPC_MESSAGE_NODE = NpcMessageNode()
NPC_INTERRUPT_NODE = NpcInterruptNode()
for _n in (NPC_CHAT_NODE, NPC_MESSAGE_NODE, NPC_INTERRUPT_NODE):
    register_conversation_node(_n)
__all__ = ['ConversationNode', 'NpcChatNode', 'NpcMessageNode', 'NpcInterruptNode', 'NPC_CHAT_NODE', 'NPC_MESSAGE_NODE', 'NPC_INTERRUPT_NODE', 'register_conversation_node', 'get_conversation_node', 'registered_conversation_names']
