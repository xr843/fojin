# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 3.x     | :white_check_mark: |
| < 3.0   | :x:                |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Instead, please report them by emailing **xr843@foxmail.com** with:

- A description of the vulnerability
- Steps to reproduce
- Potential impact

We will acknowledge receipt within **48 hours** and aim to provide a fix within **7 days** for critical issues.

## Security Measures

FoJin implements the following security practices:

- **Authentication**: JWT (HS256) with bcrypt password hashing
- **Rate limiting**: Redis-backed sliding window (200 req/min global, stricter on auth endpoints)
- **Input validation**: Pydantic v2 schema validation on all endpoints
- **SQL injection prevention**: SQLAlchemy ORM with parameterized queries
- **Security headers**: CSP, X-Frame-Options, X-Content-Type-Options via Nginx
- **Secrets management**: Environment variables, never committed to git
- **CI scanning**: Automated secret detection in GitHub Actions
- **API key encryption**: AES/Fernet for user BYOK keys

## Self-Hosting Privacy Notes

If you run `docker compose up` from a fresh clone, be aware of three defaults
that shape what leaves your machine:

1. **Frontend analytics are off by default.** No tracking script is injected
   unless you set both `VITE_UMAMI_URL` and `VITE_UMAMI_WEBSITE_ID` at build
   time (Dockerfile `ARG`s). See `.env.example`.
2. **LLM / embedding traffic goes to upstream providers by default.** The
   stock config calls DeepSeek (`LLM_API_URL`) and SiliconFlow
   (`EMBEDDING_API_URL`); user questions and document passages are sent to
   those providers. For a fully local setup, point `LLM_API_URL` /
   `EMBEDDING_API_URL` at an OpenAI-compatible local server (vLLM, Ollama,
   LM Studio) and clear the API keys, or have each user supply their own
   key via the in-app BYOK flow.
3. **The frontend container publishes its port on the docker host network,
   not just `127.0.0.1`.** Backend, Postgres, Redis, Elasticsearch, and the
   Umami container are bound to localhost; the frontend is reachable from
   anything that can hit your docker host (the LAN, in most setups). If
   that matters, put it behind an authenticated reverse proxy or change the
   `frontend.ports` mapping in `docker-compose.yml` to
   `"127.0.0.1:${FRONTEND_PORT:-3000}:80"`.
