# ============================================
# Model Router — Pick the right model per question
# ============================================

# Available models with their strengths
MODELS = {
    "fast": {
        "name": "openai/gpt-4o-mini",
        "display": "GPT-4o Mini (fast)",
        "strengths": ["simple facts", "definitions", "quick answers"],
        "cost_per_1k_tokens": 0.0,
    },
    "reasoning": {
        "name": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "display": "Nemotron (reasoning)",
        "strengths": ["math", "logic", "analysis", "multi-step"],
        "cost_per_1k_tokens": 0.0,
    },
    "balanced": {
        "name": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "display": "Nemotron (balanced)",
        "strengths": ["code", "general purpose"],
        "cost_per_1k_tokens": 0.0,
    },
}


def classify_question(user_input, mode="general"):
    """
    Classify a question to determine which model to use.
    
    Returns: "fast" | "reasoning" | "balanced"
    """
    q = user_input.lower().strip()
    
    # Mode-based defaults (the mode hints at what's needed)
    mode_defaults = {
        "sql": "balanced",        # SQL benefits from code-aware model
        "code-review": "reasoning",  # code review needs deep analysis
        "python": "balanced",     # general programming
        "ruby": "balanced",       # general programming
        "general": None,          # fall through to keyword analysis
    }
    
    mode_pref = mode_defaults.get(mode)
    
    # === HEURISTIC 1: Complex reasoning keywords ===
    reasoning_keywords = [
        "why", "explain", "analyze", "compare", "evaluate",
        "design", "architect", "trade-off", "tradeoff",
        "calculate", "compute", "solve", "prove",
        "step by step", "think through",
    ]
    if any(kw in q for kw in reasoning_keywords):
        return "reasoning"
    
    # === HEURISTIC 2: Code generation keywords ===
    code_keywords = [
        "write code", "write a function", "implement",
        "create a script", "generate code", "show me code",
        "def ", "class ", "function for",
    ]
    if any(kw in q for kw in code_keywords):
        return "balanced"
    
    # === HEURISTIC 3: Simple facts / definitions ===
    fast_indicators = [
        q.startswith("what is"),
        q.startswith("what's"),
        q.startswith("define"),
        q.startswith("who is"),
        q.startswith("when did"),
        len(q.split()) <= 6,  # very short questions
    ]
    if any(fast_indicators):
        return "fast"
    
    # === HEURISTIC 4: Fall back to mode preference or balanced ===
    if mode_pref:
        return mode_pref
    
    return "balanced"


def get_model_for_question(user_input, mode="general"):
    """Get the full model config for a question."""
    category = classify_question(user_input, mode)
    return {
        "category": category,
        **MODELS[category],
    }


def get_model_name_for_question(user_input, mode="general") -> str:
    """Return the OpenRouter model ID for an LLM API call."""
    return get_model_for_question(user_input, mode)["name"]


def explain_routing(user_input, mode="general"):
    """Return a human-readable explanation of why this model was chosen."""
    category = classify_question(user_input, mode)
    model = MODELS[category]
    
    reasons = {
        "fast": "Detected simple/factual question — using fast model for speed",
        "reasoning": "Detected reasoning/analysis question — using reasoning model",
        "balanced": "Detected code/general question — using balanced model",
    }
    
    return {
        "category": category,
        "model_name": model["display"],
        "reason": reasons[category],
    }