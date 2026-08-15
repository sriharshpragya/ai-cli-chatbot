# ============================================
# Tool Collection for Multi-Tool Agent
# 5 tools with distinct purposes
# ============================================
import json
from datetime import datetime, timezone


# ============================================
# TOOL 1: Weather (from Day 27)
# ============================================

def get_weather(city: str, unit: str = "celsius") -> dict:
    """Get current weather for a city."""
    fake_weather = {
        "Tokyo": {"temp_c": 14, "temp_f": 57, "condition": "Cloudy", "humidity": 70},
        "New York": {"temp_c": 18, "temp_f": 64, "condition": "Sunny", "humidity": 45},
        "London": {"temp_c": 10, "temp_f": 50, "condition": "Rainy", "humidity": 85},
        "Mumbai": {"temp_c": 32, "temp_f": 90, "condition": "Humid", "humidity": 90},
        "Sydney": {"temp_c": 22, "temp_f": 72, "condition": "Partly Cloudy", "humidity": 60},
    }
    
    if city not in fake_weather:
        return {"error": f"No weather data for {city}"}
    
    data = fake_weather[city]
    temp = data["temp_c"] if unit == "celsius" else data["temp_f"]
    
    return {
        "city": city,
        "temperature": temp,
        "unit": unit,
        "condition": data["condition"],
        "humidity": data["humidity"],
    }


weather_schema = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather (temperature, humidity, conditions) for a specific city. Use this when the user asks about weather, temperature, or climate conditions.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name (e.g., 'Tokyo', 'New York')"
                },
                "unit": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "description": "Temperature unit (default: celsius)"
                }
            },
            "required": ["city"]
        }
    }
}


# ============================================
# TOOL 2: Calculator
# ============================================

def calculate(operation: str, a: float, b: float) -> dict:
    """Perform basic math operations."""
    operations = {
        "add": lambda x, y: x + y,
        "subtract": lambda x, y: x - y,
        "multiply": lambda x, y: x * y,
        "divide": lambda x, y: x / y if y != 0 else None,
        "power": lambda x, y: x ** y,
    }
    
    if operation not in operations:
        return {"error": f"Unknown operation: {operation}. Available: add, subtract, multiply, divide, power"}
    
    result = operations[operation](a, b)
    
    if result is None:
        return {"error": "Cannot divide by zero"}
    
    return {
        "operation": operation,
        "a": a,
        "b": b,
        "result": result,
    }


calculator_schema = {
    "type": "function",
    "function": {
        "name": "calculate",
        "description": "Perform basic mathematical operations. Use this for arithmetic calculations, not for weather or time queries.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["add", "subtract", "multiply", "divide", "power"],
                    "description": "The mathematical operation to perform"
                },
                "a": {
                    "type": "number",
                    "description": "First number"
                },
                "b": {
                    "type": "number",
                    "description": "Second number"
                }
            },
            "required": ["operation", "a", "b"]
        }
    }
}


# ============================================
# TOOL 3: Current Time
# ============================================

def get_current_time(timezone_name: str = "UTC") -> dict:
    """Get current time in a specific timezone."""
    # Simplified - real code would use pytz or zoneinfo
    timezones = {
        "UTC": timezone.utc,
        "US/Eastern": timezone.utc,  # Simplified
        "US/Pacific": timezone.utc,  # Simplified
        "Asia/Tokyo": timezone.utc,  # Simplified
        "Asia/Kolkata": timezone.utc,  # Simplified
    }
    
    if timezone_name not in timezones:
        return {"error": f"Unknown timezone: {timezone_name}"}
    
    now = datetime.now(timezones[timezone_name])
    
    return {
        "timezone": timezone_name,
        "iso_time": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "day_of_week": now.strftime("%A"),
    }


time_schema = {
    "type": "function",
    "function": {
        "name": "get_current_time",
        "description": "Get the current date and time. Use this when the user asks about the current time, date, or day of the week.",
        "parameters": {
            "type": "object",
            "properties": {
                "timezone_name": {
                    "type": "string",
                    "enum": ["UTC", "US/Eastern", "US/Pacific", "Asia/Tokyo", "Asia/Kolkata"],
                    "description": "Timezone name"
                }
            },
            "required": []
        }
    }
}


# ============================================
# TOOL 4: Text Analyzer
# ============================================

def analyze_text(text: str) -> dict:
    """Analyze text - count words, characters, sentences."""
    if not text:
        return {"error": "Text is empty"}
    
    words = text.split()
    sentences = [s.strip() for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    
    return {
        "character_count": len(text),
        "word_count": len(words),
        "sentence_count": len(sentences),
        "average_word_length": round(sum(len(w) for w in words) / len(words), 2) if words else 0,
        "longest_word": max(words, key=len) if words else "",
    }


text_analyzer_schema = {
    "type": "function",
    "function": {
        "name": "analyze_text",
        "description": "Analyze a piece of text and get statistics like word count, character count, and sentence count. Use this when the user asks about text length, statistics, or wants to analyze written content.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to analyze"
                }
            },
            "required": ["text"]
        }
    }
}


# ============================================
# TOOL 5: Fake Email Sender
# ============================================

def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email (fake - just returns success)."""
    if "@" not in to:
        return {"error": "Invalid email address"}
    
    if not subject:
        return {"error": "Subject cannot be empty"}
    
    if not body:
        return {"error": "Email body cannot be empty"}
    
    # In real code, would call SendGrid, SES, etc.
    return {
        "status": "sent",
        "to": to,
        "subject": subject,
        "body_length": len(body),
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "message_id": f"msg_{hash(to + subject)}"[:20],
    }


email_schema = {
    "type": "function",
    "function": {
        "name": "send_email",
        "description": "Send an email to someone. Use this when the user asks to send, share, or notify someone via email.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient email address"
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line"
                },
                "body": {
                    "type": "string",
                    "description": "Email body content"
                }
            },
            "required": ["to", "subject", "body"]
        }
    }
}


# ============================================
# CONVENIENT REGISTRATION HELPER
# ============================================

ALL_TOOLS = [
    (weather_schema, get_weather),
    (calculator_schema, calculate),
    (time_schema, get_current_time),
    (text_analyzer_schema, analyze_text),
    (email_schema, send_email),
]


def register_all_tools(agent):
    """Register all tools with an agent."""
    for schema, function in ALL_TOOLS:
        agent.register_tool(schema, function)