"""
Master orchestration script for all data source imports.

Usage:
    python scripts/import_all.py --priority P0          # Run P0 imports only
    python scripts/import_all.py --priority P1          # Run P1 imports only
    python scripts/import_all.py --source gretil         # Run single source
    python scripts/import_all.py --stats                 # Show current stats
    python scripts/import_all.py                         # Run all (P0 → P3)
"""

import argparse
import asyncio
import importlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Priority → (module_name, description)
IMPORT_REGISTRY = {
    "P0": [
        ("import_catalog", "CBETA 完整目录"),
        ("import_content", "CBETA 文本内容 (--all)"),
    ],
    "P1": [
        ("import_suttacentral", "SuttaCentral 巴利经藏"),
        ("import_gretil", "GRETIL 梵文文献"),
        ("import_dsbc", "DSBC 数字梵文佛典"),
        ("import_sat", "SAT 大正藏交叉引用"),
    ],
    "P2": [
        ("import_84000", "84000 藏英翻译"),
        ("import_ddb", "DDB 电子佛学辞典"),
        ("import_korean_tripitaka", "高丽大藏经"),
        ("import_polyglotta", "多语平行文本"),
    ],
    "P3": [
        ("import_gandhari", "犍陀罗语佛典"),
        ("import_vri_tipitaka", "VRI 巴利三藏"),
        ("import_dila_authority", "DILA 权威数据"),
        ("import_buddhason", "莊春江讀經站 阿含/尼柯耶"),
    ],
}

# Source code → module name mapping
SOURCE_TO_MODULE = {}
for priority, modules in IMPORT_REGISTRY.items():
    for mod_name, desc in modules:
        # Derive source code from module name
        code = mod_name.replace("import_", "")
        SOURCE_TO_MODULE[code] = (mod_name, desc, priority)


def show_registry():
    """Print the import registry."""
    print("=" * 60)
    print("佛津 (FoJin) — Data Source Import Registry")
    print("=" * 60)
    for priority, modules in IMPORT_REGISTRY.items():
        print(f"\n  {priority}:")
        for mod_name, desc in modules:
            code = mod_name.replace("import_", "")
            print(f"    {code:25s} {desc}")
    print()


async def run_import_module(module_name: str, description: str):
    """Run a single import module's main() function."""
    print(f"\n{'─' * 50}")
    print(f"Starting: {description} ({module_name})")
    print(f"{'─' * 50}")
    try:
        mod = importlib.import_module(module_name)
        if hasattr(mod, "main"):
            # Extract default args from description, e.g. "(--all)" → ["--all"]
            default_args: list[str] = []
            m = re.search(r"\(([^)]+)\)", description)
            if m:
                default_args = m.group(1).strip().split()

            # Temporarily set sys.argv so argparse inside the module sees the args
            saved_argv = sys.argv
            sys.argv = [module_name] + default_args
            try:
                result = mod.main()
                if asyncio.iscoroutine(result):
                    await result
            finally:
                sys.argv = saved_argv
            print(f"  ✓ {description} completed.")
        else:
            print(f"  ⚠ {module_name} has no main() function. Skipping.")
    except Exception as e:
        print(f"  ✗ {description} FAILED: {e}")


async def run_stats():
    """Run the import_stats module."""
    try:
        mod = importlib.import_module("import_stats")
        result = mod.main()
        if asyncio.iscoroutine(result):
            await result
    except Exception as e:
        print(f"Stats error: {e}")


async def main():
    parser = argparse.ArgumentParser(description="FoJin data import orchestrator")
    parser.add_argument(
        "--priority",
        choices=["P0", "P1", "P2", "P3"],
        help="Run imports for a specific priority level",
    )
    parser.add_argument("--source", help="Run import for a single source code")
    parser.add_argument("--stats", action="store_true", help="Show current import statistics")
    parser.add_argument("--list", action="store_true", dest="show_list", help="List available importers")
    args = parser.parse_args()

    if args.show_list:
        show_registry()
        return

    if args.stats:
        await run_stats()
        return

    if args.source:
        if args.source in SOURCE_TO_MODULE:
            mod_name, desc, _ = SOURCE_TO_MODULE[args.source]
            await run_import_module(mod_name, desc)
        else:
            print(f"Unknown source: {args.source}")
            print(f"Available: {', '.join(sorted(SOURCE_TO_MODULE.keys()))}")
        return

    # Run by priority
    priorities = [args.priority] if args.priority else ["P0", "P1", "P2", "P3"]

    print("=" * 60)
    print(f"佛津 (FoJin) — Running imports: {', '.join(priorities)}")
    print("=" * 60)

    for priority in priorities:
        modules = IMPORT_REGISTRY.get(priority, [])
        print(f"\n{'=' * 40}")
        print(f"  Priority {priority}: {len(modules)} sources")
        print(f"{'=' * 40}")
        for mod_name, desc in modules:
            await run_import_module(mod_name, desc)

    print(f"\n{'=' * 60}")
    print("All imports completed.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
