# 🤖 AI CLI Chatbot

**Personal project: A production-grade AI chatbot with dual interfaces — interactive CLI and REST API.**

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009485)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791)
![Redis](https://img.shields.io/badge/Redis-7-DC382D)
![Docker](https://img.shields.io/badge/Docker-Multi--stage-2496ED)
[![Live](https://img.shields.io/badge/status-live-success)](https://ai-cli-chatbot-production.up.railway.app)

Built as a hands-on exploration of modern AI infrastructure patterns — applying production engineering principles (authentication, rate limiting, streaming, persistence) to a domain I was curious about.

Single codebase, dual interfaces — like Stripe's `stripe listen` CLI + Stripe API. Same business logic, two different ways to interact with it.

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



## Architecture

**Shared modules** between CLI and API:

- `router.py` — model selection logic based on question complexity
- `prompt_registry.py` — mode-specific system prompts
- `modes.py` — mode configurations
- `cost_tracker.py` — token/cost calculations
- `database/` — shared storage layer (used by API, optional for CLI)
- `cache/` — Redis rate limiting and session cache

Both interfaces call the same underlying logic — bug fixes and features stay in sync automatically.

## Two Ways to Use It



### 🖥️ CLI Mode (Great for developers)

```bash
python main.py
```

```
🤖  AI CLI Chatbot v3.0
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

## API Endpoints



### Public

- `GET /` — Health check
- `GET /health` — Deep health check (verifies DB + Redis)
- `GET /modes` — List available modes
- `POST /register` — Create user account



### Authenticated (requires `X-API-Key`)

- `GET /me` — Current user info
- `POST /me/keys` — Generate API key
- `GET /me/keys` — List your API keys
- `DELETE /me/keys/{id}` — Revoke API key
- `POST /chat` — Chat with mode routing
- `POST /chat/stream` — Streaming chat
- `GET /conversations` — List your conversations
- `GET /conversations/{id}` — Get full conversation history



## Tech Stack

- **Python 3.11** with type hints throughout
- **FastAPI 0.115** — async web framework
- **SQLAlchemy 2.0** — async ORM
- **PostgreSQL 16** — durable storage (via Docker)
- **Redis 7** — cache + rate limiting (via Docker)
- **Alembic** — database migrations
- **OpenAI SDK** — LLM integration via OpenRouter
- **bcrypt + JWT** — authentication
- **Docker** — multi-stage builds for production
- **Railway** — deployment platform



## Getting Started



### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- OpenRouter API key ([get one free](https://openrouter.ai))



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

# Run CLI
python main.py

# OR run API
uvicorn api:app --reload
```



### Environment Variables

```bash
OPENROUTER_API_KEY=your-key-here          # required for both modes
DATABASE_URL=postgresql+asyncpg://...     # optional (for API mode)
REDIS_URL=redis://localhost:6380/0        # optional (for API mode)
ENVIRONMENT=development                    # optional
DEFAULT_MODEL=openai/gpt-4o-mini          # optional
```



## Production Deployment

**🌐 Live API:** [https://ai-cli-chatbot-production.up.railway.app/](https://ai-cli-chatbot-production.up.railway.app/) 
**📖 Interactive Docs:** [https://ai-cli-chatbot-production.up.railway.app/docs](https://ai-cli-chatbot-production.up.railway.app/docs)  
**❤️ Health Check:** [https://ai-cli-chatbot-production.up.railway.app/health](https://ai-cli-chatbot-production.up.railway.app/health)

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

Try it live: register an account, generate an API key, chat with the AI.

### Try It

```bash
# Register (replace with your details)
curl -X POST https://YOUR-DOMAIN.up.railway.app/register \
  -H "Content-Type: application/json" \
  -d '{"username":"tester","email":"test@example.com","password":"secure123"}'
```

Deployment configuration lives in `Dockerfile`, `railway.json`, and `wait_for_db.py`.

## Engineering Decisions

While the domain is AI, the engineering patterns are what interested me. Key decisions:

### Why dual CLI + API?

Different use cases need different interfaces. Developers want CLI for quick iteration. Frontends need API. Sharing the same underlying modules means:

- No duplicate business logic
- Bug fixes affect both
- Features stay in sync
- Same cost model, routing, prompts

This pattern is common in developer tools (Stripe CLI + API, GitHub CLI + API, AWS CLI + API).

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

## Testing

```bash
# Test API is up
curl http://localhost:8000/

# Register a user
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"username": "test", "email": "test@example.com", "password": "securepass"}'

# Send a chat message (replace with your API key)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk_live_your_key_here" \
  -d '{"message": "What is FastAPI?", "mode": "general"}'

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
- **Security** — password hashing, API key management, rate limiting, input validation
- **Caching strategies** — Redis-backed session caching, sliding window rate limiting
- **Async programming** — non-blocking I/O, concurrent request handling
- **DevOps** — CI/CD pipelines, managed services, monitoring

Concepts I've applied in Ruby on Rails contexts (Sidekiq workers, ActiveRecord, Redis caching, background jobs), rebuilt in Python's async ecosystem.

## License

MIT

## Author

**Pragya Sriharsh** — Senior Backend Engineer  
10+ years building production systems: Ruby on Rails, Node.js, PostgreSQL, React, AWS  

- [LinkedIn](https://linkedin.com/in/pragyasriharsh)
- [GitHub](https://github.com/sriharshpragya)

