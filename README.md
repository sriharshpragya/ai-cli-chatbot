# 🤖 AI CLI Chatbot

A multi-mode AI chatbot with conversation memory, token tracking, and 5 expert personas. Built with Python and OpenAI-compatible APIs.

## Features

- **5 Expert Modes** — Switch between General Assistant, Ruby/Rails Expert, Python Tutor, SQL Expert, and Code Reviewer
- **Conversation Memory** — Full conversation history maintained across turns
- **Save & Load** — Persist conversations to JSON files and resume later
- **Token Tracking** — Real-time token usage and cost estimation per session
- **Smart History Management** — Empty responses filtered to keep conversation quality high
- **Graceful Error Handling** — Rate limits and API failures handled without crashing

## Demo

```
$ python main.py
=======================================================
🤖  AI CLI Chatbot — Week 1 Project
Built by Pragya Sriharsh
You: /mode sql
Switched to: SQL Expert
You: write a query for finding ruby developers in my company
AI: SELECT COUNT(*) AS ruby_developers
FROM employees
WHERE language = 'Ruby';
[677 tok | stop | turn 1]
You: /save sql_session
Saved to: chat_history/sql_session.json
You: /stats
Mode:     SQL Expert
Turns:    1
Tokens:   677
Est cost: $0.002031
```

## Available Modes

| Mode | Description |
|------|-------------|
| `general` | General-purpose AI assistant |
| `ruby` | Ruby/Rails expert with Rails analogies |
| `python` | Python tutor for Ruby developers |
| `sql` | PostgreSQL expert — writes and optimizes queries |
| `code-review` | Code reviewer — finds bugs, performance issues, security concerns |

## Commands

| Command | Description |
|---------|-------------|
| `/mode <name>` | Switch to a different expert mode |
| `/modes` | List all available modes |
| `/stats` | Show token usage and session stats |
| `/save [name]` | Save conversation to JSON file |
| `/load <name>` | Load a previously saved conversation |
| `/history` | List all saved conversations |
| `/reset` | Clear conversation history |
| `/help` | Show all commands |
| `/quit` | Exit the chatbot |

## Setup

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/ai-cli-chatbot.git
cd ai-cli-chatbot

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install openai python-dotenv

# Add your API key
cat > .env << 'EOF'
OPENROUTER_API_KEY=your-key-here
EOF

# Run
python main.py
```

## Tech Stack

- **Python 3.11** — Core language
- **OpenAI SDK** — LLM API client (OpenAI-compatible format)
- **OpenRouter** — Multi-model gateway (access GPT, Claude, DeepSeek, and more)
- **python-dotenv** — Secure API key management

## Architecture

main.py       → Chat loop, command handling, session management
modes.py      → System prompts for each expert persona
storage.py    → JSON-based conversation persistence
chat_history/ → Saved conversation files

## What I Learned Building This

- LLM API request/response format (OpenAI Chat Completions standard)
- Conversation memory management (the model has no memory — you manage it)
- Token tracking and cost awareness
- Handling API failures gracefully (None responses, rate limits, timeouts)
- System prompts as a powerful tool for shaping AI behavior
- Python project structure (classes, modules, error handling)

## Author

**Pragya Sriharsh** — Senior Engineering Lead transitioning into Agentic AI development.
This is Week 1 of a 26-week AI learning roadmap.

## License

MIT