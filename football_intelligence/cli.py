"""Step 1 entry point: emit or validate configuration without processing video."""

import argparse
import json
from pathlib import Path
import sys

from .config import AppConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Football Intelligence project foundation")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("default-config", help="Print default configuration as JSON")
    validate = commands.add_parser("validate-config", help="Validate and print effective configuration")
    validate.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    try:
        config = AppConfig.load(args.path) if args.command == "validate-config" else AppConfig()
    except (OSError, ValueError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(config.to_dict(), indent=2, allow_nan=False))
    return 0
