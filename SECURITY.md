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
