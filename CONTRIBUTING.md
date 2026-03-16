# Contributing to FoJin

[中文版](./docs/CONTRIBUTING_zh.md)

Thank you for your interest in contributing to FoJin! This project aims to make Buddhist texts accessible to researchers worldwide, and every contribution helps.

## Ways to Contribute

### No coding required
- **Translate the UI** — Help make FoJin accessible in your language. See [Translation Guide](#translation).
- **Add a data source** — Know a Buddhist text database we're missing? [Open an issue](https://github.com/xr843/fojin/issues/new?labels=data-source&title=New+data+source:+) with the URL and details.
- **Documentation** — Improve guides, add examples, fix typos.
- **Report bugs** — Found something broken? [File a bug report](https://github.com/xr843/fojin/issues/new?labels=bug).
- **Spread the word** — Star the repo, share it with researchers, write about it.

### Code contributions
- **Fix bugs** — Check issues labeled [`good first issue`](https://github.com/xr843/fojin/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) to get started.
- **Improve search** — Better tokenization, ranking, or multilingual support.
- **Frontend improvements** — UI/UX enhancements, accessibility, responsive design.
- **Backend features** — API endpoints, data pipelines, performance optimization.

## Getting Started

1. Fork the repo and clone your fork
2. Follow the [Development](#development) section in README.md to set up locally
3. Create a feature branch: `git checkout -b feat/your-feature`
4. Make your changes
5. Run tests: `cd backend && pytest tests/ -q`
6. Commit with a clear message
7. Push and open a Pull Request

## Code Style

- **Python**: Follow PEP 8. Use type hints. We use Pydantic for schemas.
- **TypeScript**: Follow the existing ESLint config. Use functional components with hooks.
- **Commits**: Use conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`).

## Adding a Data Source

To add a new Buddhist text data source:

1. Create `backend/scripts/import_<source_name>.py`
2. Follow the pattern of existing import scripts (see `import_suttacentral.py` as a good example)
3. Add the source to `backend/scripts/import_all.py`
4. Update the data sources table in README.md

## Reporting Issues

- Use the GitHub issue templates
- Include steps to reproduce for bugs
- For feature requests, describe the use case

## Translation

We welcome translations of both the UI and documentation. Currently supported languages and their status:

| Language | UI | Docs | Status |
|----------|-----|------|--------|
| English | ✅ | ✅ | Complete |
| 中文 (Chinese) | ✅ | ✅ | Complete |
| 日本語 (Japanese) | ❌ | ❌ | Help wanted |
| 한국어 (Korean) | ❌ | ❌ | Help wanted |
| ไทย (Thai) | ❌ | ❌ | Help wanted |
| Tiếng Việt (Vietnamese) | ❌ | ❌ | Help wanted |
| සිංහල (Sinhala) | ❌ | ❌ | Help wanted |
| Myanmar (Burmese) | ❌ | ❌ | Help wanted |

To contribute a translation:
1. Copy `frontend/src/locales/en.json` to `frontend/src/locales/<lang-code>.json`
2. Translate the values (keep the keys in English)
3. Submit a PR

## Community

- **Discord**: [Join our server](https://discord.gg/76SZeuJekq)
- **GitHub Discussions**: [Ask questions & share ideas](https://github.com/xr843/fojin/discussions)

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
