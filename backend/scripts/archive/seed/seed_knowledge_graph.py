"""DEPRECATED — use extract_structured_kg.py instead.

This wrapper exists only for backwards compatibility. It delegates
to the new idempotent extractor with all passes enabled.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

print("⚠ seed_knowledge_graph.py is deprecated. "
      "Delegating to extract_structured_kg.py...")

from scripts.extract_structured_kg import main  # noqa: E402

main()
