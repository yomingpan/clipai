from __future__ import annotations

import argparse
from pathlib import Path

from ClipAI.app.language_pack_loader import validate_official_language_packs
from ClipAI.core.errors import ActionLanguagePackError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate every official Action Language Pack.")
    parser.add_argument("--config-dir", type=Path, default=Path("config"))
    args = parser.parse_args(argv)
    try:
        packs = validate_official_language_packs(args.config_dir)
    except ActionLanguagePackError as exc:
        print(f"{exc.reason}: {exc.path}")
        return 2
    print(f"validated {len(packs)} action language pack(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
