"""Trusted Setup composition entry, alongside wheel-derived bootstrap code."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ClipAI.app.first_install_bootstrap import main

raise SystemExit(main(bootstrap_root=Path(__file__).resolve().parent.parent,
                     environment=dict(os.environ)))
