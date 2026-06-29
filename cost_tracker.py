# ============================================
# Cost tracking for the chatbot
# Tracks every LLM call with full cost breakdown
# ============================================
from datetime import datetime
import json
import os

# Pricing per 1M tokens (paid models)
# Free models cost $0, but we still track tokens for analytics
MODEL_PRICING = {
    "google/gemma-3-27b-it:free": {"input": 0.00, "output": 0.00},
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free": {"input": 0.00, "output": 0.00},
    "deepseek/deepseek-v4-flash:free": {"input": 0.00, "output": 0.00},
    "anthropic/claude-sonnet-4": {"input": 3.00, "output": 15.00},
    "openai/gpt-4o": {"input": 2.50, "output": 10.00},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
}


class CostTracker:
    """Tracks LLM call costs across the session."""
    
    def __init__(self, log_file="cost_log.json"):
        self.calls = []
        self.log_file = log_file
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0
    
    def log_call(self, model, prompt_tokens, completion_tokens, finish_reason, operation="chat"):
        """Log a single LLM call."""
        pricing = MODEL_PRICING.get(model, {"input": 0, "output": 0})
        
        input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]
        call_cost = input_cost + output_cost
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "operation": operation,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "input_cost_usd": input_cost,
            "output_cost_usd": output_cost,
            "total_cost_usd": call_cost,
            "finish_reason": finish_reason,
        }
        
        self.calls.append(entry)
        self.total_input_tokens += prompt_tokens
        self.total_output_tokens += completion_tokens
        self.total_cost += call_cost
        
        return entry
    
    def get_summary(self):
        """Get session summary stats."""
        return {
            "total_calls": len(self.calls),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "total_cost_usd": self.total_cost,
            "avg_tokens_per_call": (
                (self.total_input_tokens + self.total_output_tokens) / len(self.calls)
                if self.calls else 0
            ),
        }
    
    def get_per_model_breakdown(self):
        """Show which models are used and their cost contribution."""
        breakdown = {}
        for call in self.calls:
            model = call["model"]
            if model not in breakdown:
                breakdown[model] = {
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost": 0.0,
                }
            breakdown[model]["calls"] += 1
            breakdown[model]["input_tokens"] += call["prompt_tokens"]
            breakdown[model]["output_tokens"] += call["completion_tokens"]
            breakdown[model]["cost"] += call["total_cost_usd"]
        return breakdown
    
    def save_log(self):
        """Persist call log to JSON for later analysis."""
        with open(self.log_file, "w") as f:
            json.dump(self.calls, f, indent=2)
    
    def format_call_display(self, call):
        """Format a single call for display after each response."""
        return (
            f"   [{call['total_tokens']} tok | "
            f"in:{call['prompt_tokens']} out:{call['completion_tokens']} | "
            f"${call['total_cost_usd']:.6f} | "
            f"{call['finish_reason']}]"
        )