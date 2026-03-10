# Contributing to FoJin

Thank you for your interest in contributing to FoJin! This project aims to make Buddhist texts accessible to researchers worldwide, and every contribution helps.

## Ways to Contribute

- **Add a data source** — Know a Buddhist text database we're missing? Open an issue or submit an import script.
- **Improve search** — Better tokenization, ranking, or multilingual support.
- **Fix bugs** — Check the [issues](https://github.com/xr843/fojin/issues) page.
- **Translate** — Help translate the UI or documentation.
- **Documentation** — Improve guides, add examples, fix typos.

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

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
