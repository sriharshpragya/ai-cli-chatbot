# 🤖 AI CLI Chatbot + Agent

**Personal project: A production-grade AI platform with triple interfaces — interactive CLI, REST API, and NEW: AI Agent with 14 tools.**

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009485)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791)
![Redis](https://img.shields.io/badge/Redis-7-DC382D)
![Docker](https://img.shields.io/badge/Docker-Multi--stage-2496ED)
![Agent](https://img.shields.io/badge/Agent-14_tools-orange)
[![Live](https://img.shields.io/badge/status-live-success)](https://ai-cli-chatbot-production.up.railway.app)

Built as a hands-on exploration of modern AI infrastructure patterns — applying production engineering principles (authentication, rate limiting, streaming, persistence, function calling) to a domain I was curious about.

Single codebase, triple interfaces — like Stripe's `stripe listen` CLI + Stripe API + Stripe SDKs. Same business logic, three different ways to interact with it.

**Evolution:** v1.0 CLI Chatbot → v2.0 REST API → v3.0 Production Hardening → **v3.1 AI Agent (current)**

## Features



### Interactive CLI Mode

- **Multiple personas** (general, ruby, python, sql, code-review)
- **Smart model routing** — automatically picks the right model based on question complexity
- **Streaming responses** — see AI think in real-time
- **Conversation memory** with sliding window management
- **Cost tracking** per session with detailed breakdowns
- **Session save/load** — resume conversations later
- **Command system** (`/mode`, `/save`, `/cost`, `/help`)



### Production REST API Mode

- **Authentication** via API keys (bcrypt-hashed with prefix indexing)
- **Rate limiting** with Redis-backed sliding window (multi-worker safe)
- **Streaming** via Server-Sent Events (SSE)
- **PostgreSQL** persistence for users, keys, conversations, messages
- **Cost tracking** per message in database
- **Auto-generated docs** at `/docs` (Swagger UI)
- **Auto-deploy** from GitHub to Railway



### 🤖 AI Agent Mode (NEW in v3.1)

- **14 tools available** — weather, calculator, GitHub, file reader, URL fetcher, and more
- **Function calling** — LLM automatically selects and uses tools
- **Multi-tool orchestration** — chains multiple tools in a single query
- **Real API integrations** — GitHub API for repos, issues, search
- **Interactive CLI mode** (`python main.py --agent`)
- **REST API endpoints** — `POST /agent`, `GET /agent/tools`
- **Reuses production hardening** — same multi-provider fallback, circuit breakers, retry logic



## Architecture

**Shared modules** across CLI, API, and Agent:

- `llm_client.py` — multi-provider LLM with fallback (OpenRouter → Groq), circuit breakers, retry
- `router.py` — model selection logic based on question complexity
- `prompt_registry.py` — mode-specific system prompts
- `modes.py` — mode configurations
- `cost_tracker.py` — token/cost calculations
- `agent.py` — reusable Agent class with tool orchestration
- `tools/` — 14 tools (basic, GitHub, file/URL)
- `database/` — shared storage layer (used by API, optional for CLI)
- `cache/` — Redis rate limiting and session cache

All three interfaces call the same underlying logic — bug fixes and features stay in sync automatically.

## Three Ways to Use It



### 🖥️ CLI Chatbot Mode (Great for developers)

```bash
python main.py
```

```
🤖  AI CLI Chatbot v3.1
Type /help for commands

You > /mode ruby
Switched to Ruby expert mode

You > How do I use ActiveRecord validations?
AI > In Rails, validations ensure data integrity...
    Model: nvidia/llama-3.1-nemotron-70b-instruct
    Cost: $0.0023

You > /cost
Session cost: $0.0089 (4 messages, 1,247 tokens)

You > /save my_ruby_session
Saved to sessions/my_ruby_session.json
```



### 🌐 API Mode (For integration)

```bash
uvicorn api:app --reload
# Visit http://localhost:8000/docs
```

```bash
curl -X POST http://localhost:8000/chat \
  -H "X-API-Key: sk_live_your_key" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain Python decorators",
    "mode": "python",
    "max_tokens": 500
  }'
```

**Response:**

```json
{
  "response": "Decorators are a way to modify functions...",
  "conversation_id": "550e8400-e29b-41d4",
  "mode": "python",
  "model_used": "openai/gpt-4o-mini",
  "tokens": 342,
  "cost_usd": "$0.000107",
  "calls_remaining_today": 998
}
```



### 📡 Streaming API

```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "X-API-Key: sk_live_your_key" \
  -H "Content-Type: application/json" \
  -d '{"message": "Explain async/await", "mode": "python"}'
```

Returns Server-Sent Events (SSE) — real-time streaming for chat UIs.



### 🤖 AI Agent Mode (NEW)

**Interactive CLI:**

```bash
python main.py --agent
```

```
============================================================
🤖 AI PERSONAL ASSISTANT AGENT
============================================================
Model: openai/gpt-4o-mini
Available tools: 14
Max iterations: 10

Commands:
  quit, exit  - Exit the agent
  /tools      - List available tools
  /reset      - Clear conversation history
  /history    - Show conversation history
  /help       - Show this help
============================================================

💬 You: What is the weather in Tokyo and my top 3 GitHub repos?

🔧 Tools used: get_weather, get_my_repos
📊 Iterations: 2 | Tokens: 1245 | Provider: openrouter | Duration: 3421ms

🤖 Agent: The weather in Tokyo is 14°C and cloudy. Your top 3 GitHub 
repositories are: 
1. ai-cli-chatbot (Python) - 15 stars
2. ai-chat-api (Python) - 8 stars  
3. rails-utilities (Ruby) - 5 stars
```

**API:**

```bash
curl -X POST http://localhost:8000/agent \
  -H "X-API-Key: sk_live_your_key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Search GitHub for AI agent projects and summarize the top 3",
    "max_iterations": 5
  }'
```

**Response:**

```json
{
  "response": "Here are the top 3 AI agent projects on GitHub: ...",
  "tools_used": ["search_repos", "get_repo_details"],
  "iterations": 3,
  "total_tokens": 1834,
  "provider_used": "openrouter",
  "model_used": "openai/gpt-4o-mini",
  "duration_ms": 4521.3
}
```



## Available Agent Tools

### Basic Tools (5)
- `get_weather` - Current weather for any city
- `calculate` - Math operations
- `get_current_time` - Date/time in any timezone
- `analyze_text` - Word count, sentence stats
- `send_email` - Send emails (simulated)

### File & Web Tools (2)
- `read_file` - Safely read local text files (with path traversal protection)
- `fetch_url` - Fetch and extract content from URLs (with SSRF prevention)

### GitHub Integration (7)
- `list_user_repos` - Any GitHub user's public repos
- `get_repo_issues` - Repository issues
- `get_repo_details` - Detailed repo information
- `search_repos` - Search GitHub repositories
- `get_my_profile` - Your GitHub profile
- `get_my_repos` - Your repositories (public + private)
- `get_repo_readme` - Repository README content



## API Endpoints



### Public

- `GET /` — Health check
- `GET /health` — Deep health check (verifies DB + Redis)
- `GET /modes` — List available modes
- `POST /register` — Create user account
- `GET /health/agent` — Agent system status (NEW)



### Authenticated (requires `X-API-Key`)

**Chatbot:**
- `GET /me` — Current user info
- `POST /me/keys` — Generate API key
- `GET /me/keys` — List your API keys
- `DELETE /me/keys/{id}` — Revoke API key
- `POST /chat` — Chat with mode routing
- `POST /chat/stream` — Streaming chat
- `GET /conversations` — List your conversations
- `GET /conversations/{id}` — Get full conversation history

**Agent (NEW):**
- `POST /agent` — Send query to AI agent
- `GET /agent/tools` — List all available tools



## Tech Stack

- **Python 3.11** with type hints throughout
- **FastAPI 0.115** — async web framework
- **SQLAlchemy 2.0** — async ORM
- **PostgreSQL 16** — durable storage (via Docker)
- **Redis 7** — cache + rate limiting (via Docker)
- **Alembic** — database migrations
- **OpenAI SDK** — LLM integration via OpenRouter
- **BeautifulSoup4** — HTML parsing for URL fetcher (NEW)
- **Tenacity** — retry logic with exponential backoff
- **aiobreaker** — circuit breakers per LLM provider
- **structlog** — structured JSON logging
- **prometheus_client** — metrics exposition
- **bcrypt + JWT** — authentication
- **Docker** — multi-stage builds for production
- **Railway** — deployment platform



## Getting Started



### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- OpenRouter API key ([get one free](https://openrouter.ai))
- GitHub Personal Access Token (optional, for agent GitHub tools)



### Setup

```bash
# Clone
git clone https://github.com/sriharshpragya/ai-cli-chatbot.git
cd ai-cli-chatbot

# Start services (PostgreSQL + Redis in Docker)
docker-compose up -d

# Setup Python
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — add your OPENROUTER_API_KEY

# Run migrations
alembic upgrade head

# Bootstrap first user + API key (for API mode)
python bootstrap_key.py

# Run CLI Chatbot
python main.py

# OR run Agent Mode (NEW)
python main.py --agent

# OR run API
uvicorn api:app --reload
```



### Environment Variables

```bash
# Required
OPENROUTER_API_KEY=your-key-here          # required for all modes

# Optional - API mode
DATABASE_URL=postgresql+asyncpg://...     # for API mode
REDIS_URL=redis://localhost:6380/0        # for API mode
ENVIRONMENT=development                    # dev/production
DEFAULT_MODEL=openai/gpt-4o-mini          # LLM default

# Optional - Resilience (NEW in v3.0)
GROQ_API_KEY=your-groq-key                # fallback provider

# Optional - Agent (NEW in v3.1)
AGENT_ENABLED=true                         # enable agent mode
AGENT_MAX_ITERATIONS=10                    # max tool call rounds
AGENT_DEFAULT_MODEL=openai/gpt-4o-mini    # model for agent
GITHUB_TOKEN=ghp_your_github_token        # for GitHub tools
```



## Production Deployment

**🌐 Live API:** [https://ai-cli-chatbot-production.up.railway.app/](https://ai-cli-chatbot-production.up.railway.app/) 
**📖 Interactive Docs:** [https://ai-cli-chatbot-production.up.railway.app/docs](https://ai-cli-chatbot-production.up.railway.app/docs)  
**❤️ Health Check:** [https://ai-cli-chatbot-production.up.railway.app/health](https://ai-cli-chatbot-production.up.railway.app/health)
**🤖 Agent Health:** [https://ai-cli-chatbot-production.up.railway.app/health/agent](https://ai-cli-chatbot-production.up.railway.app/health/agent)

Deployed on Railway with production-grade infrastructure:

- **Auto-deploy** from `main` branch via GitHub webhooks
- **Managed PostgreSQL 16** for durable storage
- **Managed Redis 7** for cache and rate limiting
- **HTTPS** with automatic SSL certificate management
- **Health checks** for zero-downtime deploys
- **Wait-for-database logic** for proper startup ordering
- **Multi-stage Docker build** (~200MB image, no dev tools in production)
- **Non-root container user** for security
- **Version-pinned dependencies** for reproducible builds
- **Automatic Alembic migrations** on deploy

Try it live: register an account, generate an API key, chat with the AI or query the agent.

### Try It

```bash
# Register (replace with your details)
curl -X POST https://ai-cli-chatbot-production.up.railway.app/register \
  -H "Content-Type: application/json" \
  -d '{"username":"tester","email":"test@example.com","password":"secure123"}'

# Chat mode
curl -X POST https://ai-cli-chatbot-production.up.railway.app/chat \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "mode": "general"}'

# Agent mode (NEW)
curl -X POST https://ai-cli-chatbot-production.up.railway.app/agent \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the weather in Pune?"}'
```

Deployment configuration lives in `Dockerfile`, `railway.json`, and `wait_for_db.py`.

## Engineering Decisions

While the domain is AI, the engineering patterns are what interested me. Key decisions:

### Why dual CLI + API? (Now triple with Agent)

Different use cases need different interfaces. Developers want CLI for quick iteration. Frontends need API. AI applications need agents. Sharing the same underlying modules means:

- No duplicate business logic
- Bug fixes affect all interfaces
- Features stay in sync
- Same cost model, routing, prompts
- Agent inherits all production hardening automatically

This pattern is common in developer tools (Stripe CLI + API, GitHub CLI + API, AWS CLI + API + SDKs).

### Why add an Agent to a chatbot?

Modern LLM applications are shifting from "answer questions" to "do things." An agent can:

- Call real APIs (GitHub, weather services, etc.)
- Chain multiple tool calls automatically
- Handle multi-step workflows
- Extract structured data from unstructured input

Building the agent on top of the existing chatbot infrastructure meant it inherits all the production hardening (multi-provider LLM fallback, circuit breakers, retry, metrics) for free. Adding features to production-ready systems is more valuable than building from scratch.

### Why sliding window rate limiting?

Fixed window rate limits fail at boundary conditions (attacker can 2× the limit by timing bursts around the reset). Sliding window uses timestamps in Redis sorted sets for accurate enforcement across any 60-second period.

### Why Redis for rate limits?

In-memory counters break with multiple workers — each worker has its own state. Redis provides shared state, so `5/min` stays `5/min` regardless of worker count.

Same problem exists in Rails multi-server deployments — I've hit it before with Sidekiq counters and solved it with Redis. The Python approach translates the same pattern.

### Why hash API keys?

Bcrypt-hashed keys can't be recovered if the database is compromised. Combined with prefix indexing, we can efficiently find candidate keys then verify against the hash.

Same principle as `has_secure_password` in Rails — never store plaintext credentials.

### Why async everywhere?

LLM calls are I/O-bound (waiting on network). Async lets one worker handle hundreds of concurrent requests by interleaving them. Same worker serves 100x more users compared to sync equivalents.

Rails uses different concurrency models (Puma threads, Sidekiq processes) — this project was a chance to learn async/await patterns applied to I/O-heavy workloads.

### Why security-first agent tools?

The file reader and URL fetcher tools could easily become attack vectors. Applied production security principles:

- **File reader:** Path traversal prevention, size limits, extension whitelist, binary detection
- **URL fetcher:** SSRF prevention (blocks localhost, private IPs, AWS metadata endpoint), timeouts, size limits, content-type filtering

Same defensive coding practices from web app development, applied to AI tool integrations.

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run only unit tests (fast, no LLM calls)
pytest tests/ -v -m "not integration"

# Run integration tests (uses real LLM)
pytest tests/ -v -m "integration"
```

**Current coverage:** 31 tests
- 15 existing chatbot tests
- 16 new agent tests  
- 2 integration tests (real LLM calls)

Manual testing:

```bash
# Test API is up
curl http://localhost:8000/

# Test agent health
curl http://localhost:8000/health/agent

# Register a user
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"username": "test", "email": "test@example.com", "password": "securepass"}'

# Send a chat message (replace with your API key)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk_live_your_key_here" \
  -d '{"message": "What is FastAPI?", "mode": "general"}'

# Send an agent query (NEW)
curl -X POST http://localhost:8000/agent \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk_live_your_key_here" \
  -d '{"query": "What is the weather in Tokyo?"}'

# Test rate limiting (should get 429 after 5 requests)
for i in {1..8}; do
    curl -s -w "  Status: %{http_code}\n" -o /dev/null \
        -X POST http://localhost:8000/chat \
        -H "X-API-Key: $KEY" \
        -H "Content-Type: application/json" \
        -d '{"message": "hi", "mode": "general"}'
done
```



## What This Project Demonstrates

- **API design** — RESTful endpoints, proper HTTP status codes, versioning, OpenAPI documentation
- **Database engineering** — schema design, migrations, indexing, N+1 prevention, connection pooling
- **Production infrastructure** — Docker containerization, environment configuration, health checks, zero-downtime deploys
- **Security** — password hashing, API key management, rate limiting, input validation, SSRF prevention, path traversal blocks
- **Caching strategies** — Redis-backed session caching, sliding window rate limiting
- **Async programming** — non-blocking I/O, concurrent request handling
- **Resilience patterns** — multi-provider fallback, circuit breakers, retry logic (v3.0)
- **AI/LLM engineering** — function calling, multi-tool orchestration, structured outputs, agent design (v3.1)
- **DevOps** — CI/CD pipelines, managed services, monitoring, Prometheus metrics

Concepts I've applied in Ruby on Rails contexts (Sidekiq workers, ActiveRecord, Redis caching, background jobs), rebuilt in Python's async ecosystem, then extended with modern AI patterns.

## Project Evolution

| Version | Focus | Key Additions |
|---------|-------|---------------|
| **v1.0** | CLI Foundation | Multi-mode chatbot, cost tracking, session save/load |
| **v2.0** | Multi-tenant API | FastAPI, PostgreSQL, authentication, rate limiting |
| **v3.0** | Production Hardening | Multi-provider LLM, circuit breakers, retry, metrics |
| **v3.1** | AI Agent | 14 tools, function calling, orchestration ← **Current** |

Each version built on the previous, showing continuous evolution and deepening technical capabilities.

## License

MIT

## Author

**Pragya Sriharsh** — Senior Backend Engineer  
10+ years building production systems: Ruby on Rails, Node.js, PostgreSQL, React, AWS  
Currently building production AI agents

- [LinkedIn](https://linkedin.com/in/pragyasriharsh)
- [GitHub](https://github.com/sriharshpragya)
