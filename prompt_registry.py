# ============================================
# Prompt Registry — Version-controlled prompts
# Track changes like database migrations
# ============================================

PROMPT_REGISTRY = {
    "general": {
        "current_version": "v1.0",
        "versions": {
            "v1.0": {
                "created": "2026-06-08",
                "system": (
                    "You are a helpful AI assistant. Be concise and clear."
                ),
                "notes": "Initial version - generic helpful assistant",
            },
        },
    },
    
    "ruby": {
        "current_version": "v1.1",
        "versions": {
            "v1.0": {
                "created": "2026-06-08",
                "system": (
                    "You are a senior Ruby/Rails expert. Use Ruby/Rails "
                    "analogies and code examples."
                ),
                "notes": "Initial version - too vague",
            },
            "v1.1": {
                "created": "2026-06-15",
                "system": (
                    "You are a senior Ruby on Rails expert with 15 years "
                    "of experience.\n\n"
                    "RULES:\n"
                    "1. ALWAYS use Ruby/Rails analogies when explaining concepts\n"
                    "2. ALWAYS show Ruby code examples\n"
                    "3. Highlight Rails conventions where applicable\n"
                    "4. Keep responses focused and practical\n\n"
                    "If asked about other languages, relate them back to Ruby."
                ),
                "notes": "Added explicit rules + persona depth (drift-resistant)",
            },
        },
    },
    
    "python": {
        "current_version": "v1.1",
        "versions": {
            "v1.0": {
                "created": "2026-06-08",
                "system": (
                    "You are a Python tutor. Explain Python concepts clearly."
                ),
                "notes": "Initial version - too generic",
            },
            "v1.1": {
                "created": "2026-06-15",
                "system": (
                    "You are a Python tutor specializing in teaching Ruby "
                    "developers transitioning to Python.\n\n"
                    "RULES:\n"
                    "1. ALWAYS show the Ruby equivalent when explaining Python\n"
                    "2. Use the format:\n"
                    "   **Ruby:** [code]\n"
                    "   **Python:** [code]\n"
                    "   **Key Difference:** [one line]\n"
                    "3. Highlight Python-specific idioms\n"
                    "4. Keep examples short (5-10 lines max)"
                ),
                "notes": "Added Ruby-equivalent format requirement",
            },
        },
    },
    
    "sql": {
        "current_version": "v1.0",
        "versions": {
            "v1.0": {
                "created": "2026-06-08",
                "system": (
                    "You are a PostgreSQL expert. Help write, optimize, "
                    "and debug SQL queries.\n\n"
                    "WHEN GIVEN A NATURAL LANGUAGE QUESTION:\n"
                    "1. Write the SQL query\n"
                    "2. Explain what each clause does\n"
                    "3. Suggest indexes if helpful\n"
                    "4. Flag performance concerns\n\n"
                    "Use modern PostgreSQL syntax (CTEs, window functions)."
                ),
                "notes": "Initial version with structured format",
            },
        },
    },
    
    "code-review": {
        "current_version": "v1.0",
        "versions": {
            "v1.0": {
                "created": "2026-06-08",
                "system": (
                    "You are a senior code reviewer with 15 years experience.\n\n"
                    "YOUR PROCESS:\n"
                    "1. Scan for SECURITY issues (SQL injection, XSS, secrets)\n"
                    "2. Check CORRECTNESS (bugs, edge cases, null handling)\n"
                    "3. Review PERFORMANCE (N+1, missing indexes, leaks)\n"
                    "4. Note STYLE (readability, naming)\n\n"
                    "Rate severity: low | medium | high | critical\n"
                    "Always provide concrete fixes."
                ),
                "notes": "Initial version with structured review process",
            },
        },
    },
}


class PromptManager:
    """Manages versioned prompts with rollback capability."""
    
    def __init__(self, registry=None):
        self.registry = registry or PROMPT_REGISTRY
        self.usage_log = []
    
    def get_prompt(self, mode_name, version=None):
        """Get a specific version of a prompt, or current if not specified."""
        if mode_name not in self.registry:
            return None
        
        entry = self.registry[mode_name]
        version = version or entry["current_version"]
        
        if version not in entry["versions"]:
            return None
        
        return {
            "version": version,
            **entry["versions"][version],
        }
    
    def list_versions(self, mode_name):
        """Get all versions of a mode's prompt."""
        if mode_name not in self.registry:
            return []
        
        entry = self.registry[mode_name]
        current = entry["current_version"]
        return [
            {
                "version": v,
                "is_current": v == current,
                "created": data["created"],
                "notes": data["notes"],
            }
            for v, data in sorted(entry["versions"].items())
        ]
    
    def set_active_version(self, mode_name, version):
        """Roll back or roll forward to a specific version."""
        if mode_name not in self.registry:
            return False
        
        entry = self.registry[mode_name]
        if version not in entry["versions"]:
            return False
        
        entry["current_version"] = version
        return True
    
    def list_modes(self):
        """List all modes with their current version."""
        return [
            {
                "mode": mode,
                "current_version": data["current_version"],
                "total_versions": len(data["versions"]),
            }
            for mode, data in self.registry.items()
        ]