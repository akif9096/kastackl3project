# decoder.py
from typing import Dict, Any

def advanced_decode_packet(packet: Dict[str, Any]) -> str:
    """
    Transforms a compressed semantic JSON packet back into a structured, 
    human-readable, and highly visible alert message.
    """
    is_safe_crit = packet.get("safe_crit", False)
    urgency = packet.get("urg", "normal")
    actions = packet.get("act", [])
    entities = packet.get("ent", {})
    negations = packet.get("neg", [])

    # 1. Base Alert Prefix (Adding Visual Emojis for better UX)
    prefix = ""
    if is_safe_crit:
        prefix += "🚨 [SAFETY-CRITICAL ALERT] "
    elif urgency == "high":
        prefix += "⚠️ [URGENT] "

    # 2. Formulate Restrictions/Negations
    restriction_text = ""
    if negations:
        restriction_text = f"CRITICAL RESTRICTION: {'; '.join(negations).upper()}. "

    # 3. Formulate Action
    action_text = ""
    if actions:
        action_text = f"Required Action(s): {', '.join([act.title() for act in actions])}. "

    # 4. Formulate Context/Entities
    context_parts = []
    if entities.get("per"):
        context_parts.append(f"Personnel: {', '.join(entities['per'])}")
    if entities.get("loc"):
        context_parts.append(f"Location: {', '.join(entities['loc'])}")
    if entities.get("time"):
        context_parts.append(f"Timeframe: {', '.join(entities['time'])}")
    if entities.get("qty"):
        context_parts.append(f"Quantities: {', '.join(entities['qty'])}")
    if entities.get("obj"):
        context_parts.append(f"Objects/Assets: {', '.join(entities['obj'])}")
    
    context_text = ""
    if context_parts:
        context_text = f"Context Details -> {' | '.join(context_parts)}."

    # 5. Combine all parts logically
    reconstructed_message = f"{prefix}{restriction_text}{action_text}{context_text}".strip()
    
    # Fallback for empty packets
    if not reconstructed_message:
        return "Acknowledge: System status normal."
        
    return reconstructed_message