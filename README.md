# 🤖 AI CLI Chatbot

A multi-mode AI chatbot with conversation memory, token tracking, and 5 expert personas — built with Python and OpenAI-compatible APIs.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## Features

- **5 Expert Modes** — Switch between General Assistant, Ruby/Rails Expert, Python Tutor, SQL Expert, and Code Reviewer
- **Conversation Memory** — Full conversation history maintained across turns with smart filtering
- **Save & Load** — Persist conversations to JSON files and resume later
- **Token Tracking** — Real-time token usage and cost estimation per session
- **History Management** — Empty responses filtered automatically to keep conversation quality high
- **Graceful Error Handling** — Rate limits, timeouts, and API failures handled without crashing

## Demo

```
$ python main.py

=======================================================
  🤖  AI CLI Chatbot — Week 1 Project
  Built by Pragya Sriharsh
=======================================================

  Mode: General Assistant
  Type /help for commands

You: /mode sql
  Switched to: SQL Expert

You: write a query for finding ruby developers in my company

AI: SELECT COUNT(*) AS ruby_developers
    FROM employees
    WHERE language = 'Ruby';

    Index suggestion:
    CREATE INDEX idx_employees_language ON employees (language);
   [677 tok | stop | turn 1]

You: /stats
  Mode:     SQL Expert
  Turns:    1
  Tokens:   677
  Est cost: $0.002031

You: /save sql_session
  Saved to: chat_history/sql_session.json
```

## Architecture

<p align="center">
  <img src="architecture.svg" alt="Architecture Diagram" width="700"/>
</p>

The flow shows:
User input → Command router (detects / commands vs regular messages) → branches into command handlers (mode, stats, save, load, reset, history) or chat engine (ChatSession class) → which uses system prompts from modes.py and calls OpenRouter API → returns response with stats (content, tokens, finish reason). Save/load commands connect to JSON storage.

```
main.py       → Chat loop, command routing, session management
modes.py      → System prompts for 5 expert personas
storage.py    → JSON-based conversation persistence
chat_history/ → Saved conversation files (gitignored)
```



## Available Modes

| Mode | Command | Description |
|------|---------|-------------|
| General Assistant | `/mode general` | General-purpose AI assistant |
| Ruby/Rails Expert | `/mode ruby` | Explains concepts using Ruby/Rails analogies |
| Python Tutor | `/mode python` | Teaches Python with Ruby comparisons side by side |
| SQL Expert | `/mode sql` | Writes and optimizes PostgreSQL queries with index suggestions |
| Code Reviewer | `/mode code-review` | Reviews code for bugs, performance, style, and security |

## All Commands

| Command | Description |
|---------|-------------|
| `/mode <name>` | Switch to a different expert mode |
| `/modes` | List all available modes |
| `/stats` | Show token usage and session statistics |
| `/save [name]` | Save conversation to a JSON file |
| `/load <name>` | Load a previously saved conversation |
| `/history` | List all saved conversations |
| `/reset` | Clear conversation history and start fresh |
| `/help` | Show all available commands |
| `/quit` | Exit the chatbot |

## Setup

```bash
# Clone the repo
git clone https://github.com/sriharshpragya/ai-cli-chatbot.git
cd ai-cli-chatbot

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install openai python-dotenv

# Add your API key (get one free at openrouter.ai)
cat > .env << 'EOF'
OPENROUTER_API_KEY=your-key-here
EOF

# Run
python main.py
```

## Tech Stack

- **Python 3.11** — Core language
- **OpenAI SDK** — LLM API client (OpenAI-compatible format)
- **OpenRouter** — Multi-model gateway (access GPT, Claude, DeepSeek, Gemma, and more via one API)
- **python-dotenv** — Secure API key management
- **JSON** — Lightweight conversation persistence

## Key Design Decisions

**Why OpenRouter?** — Single API format works with 100+ models. Switch models by changing one string. No vendor lock-in.

**Why filter empty responses?** — Empty/None assistant responses in conversation history degrade future answer quality. The model sees failed turns and its responses get worse. Smart filtering keeps history clean.

**Why track tokens?** — Token awareness is essential for production AI apps. Every API call has a cost. This chatbot makes that cost visible from day one.

**Why system prompts for modes?** — System prompts are the simplest and most powerful way to shape AI behavior. No fine-tuning needed — just clear instructions. Each mode demonstrates how the same model produces vastly different outputs based on the system prompt.

## What I Learned Building This

- LLM APIs use a messages array format — the model has no memory, you manage conversation history
- System prompts are powerful enough to create distinct expert personas without fine-tuning
- Token costs grow with every conversation turn (entire history is re-sent each time)
- Always check for None content — API success (HTTP 200) doesn't guarantee useful output
- The `.get()` method returns None (not the default) when a key exists with a null value
- Free models have rate limits and inconsistent availability — fallback models are essential
- Exponential backoff prevents thundering herd problems when retrying failed requests

## Author

**Pragya Sriharsh** — Senior Engineering Lead at Persistent Systems, transitioning into Agentic AI development. 10+ years of backend experience with Ruby/Rails, Node.js, PostgreSQL, and AWS.

This is Week 1 of a [26-week Agentic AI learning roadmap](https://github.com/sriharshpragya).

## License

MIT
