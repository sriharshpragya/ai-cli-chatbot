# ============================================
# Stage 3: Conversation Storage
# ============================================
import json
import os
from datetime import datetime

HISTORY_DIR = "chat_history"

def ensure_history_dir():
    """Create chat_history directory if it doesn't exist."""
    os.makedirs(HISTORY_DIR, exist_ok=True)

def save_conversation(messages, mode, stats, filename=None):
    """Save conversation to a JSON file."""
    ensure_history_dir()
    
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chat_{timestamp}.json"
    
    if not filename.endswith(".json"):
        filename += ".json"
    
    filepath = os.path.join(HISTORY_DIR, filename)
    
    data = {
        "saved_at": datetime.now().isoformat(),
        "mode": mode,
        "stats": stats,
        "messages": messages,
    }
    
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    
    return filepath

def load_conversation(filename):
    """Load a conversation from a JSON file."""
    if not filename.endswith(".json"):
        filename += ".json"
    
    filepath = os.path.join(HISTORY_DIR, filename)
    
    if not os.path.exists(filepath):
        return None
    
    with open(filepath, "r") as f:
        data = json.load(f)
    
    return data

def list_conversations():
    """List all saved conversations."""
    ensure_history_dir()
    
    files = sorted(
        [f for f in os.listdir(HISTORY_DIR) if f.endswith(".json")],
        reverse=True  # newest first
    )
    
    conversations = []
    for filename in files:
        filepath = os.path.join(HISTORY_DIR, filename)
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            conversations.append({
                "filename": filename,
                "saved_at": data.get("saved_at", "unknown"),
                "mode": data.get("mode", "unknown"),
                "turns": data.get("stats", {}).get("turns", 0),
                "tokens": data.get("stats", {}).get("total_tokens", 0),
            })
        except (json.JSONDecodeError, KeyError):
            conversations.append({
                "filename": filename,
                "saved_at": "error reading file",
                "mode": "unknown",
                "turns": 0,
                "tokens": 0,
            })
    
    return conversations