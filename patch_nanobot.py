#!/usr/bin/env python3
"""Build a nanobot fork with the Delta Chat channel baked in.

Copies the nanobot source into a fresh directory, drops this repo's
``nanobot_channel_deltachat/`` package into ``nanobot/channels/deltachat/``,
patches ``pyproject.toml`` so the Delta Chat runtime dependencies are pulled in,
and optionally installs the result with ``uv tool install``.

Examples
--------
    uv run patch_nanobot.py /path/to/nanobot /path/to/nanobot-with-deltachat
    uv run patch_nanobot.py /path/to/nanobot /path/to/nanobot-with-deltachat --install
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
CHANNEL_SRC = REPO_ROOT / "nanobot_channel_deltachat"

# Runtime requirements declared by the Delta Chat channel. They are added to
# nanobot's core dependencies so ``uv tool install`` resolves them at build time
# (the manifest's lazy installer is unreliable inside a uv tool environment).
DELTACHAT_REQUIREMENTS = (
    "deltachat-rpc-client>=2.54.0",
    "deltachat-rpc-server>=2.54.0",
)

_IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".mypy_cache", ".ruff_cache", "dist"}


def _ignore(dirpath: str, names: list[str]) -> set[str]:
    return {name for name in names if name in _IGNORE_DIRS}


def log(msg: str) -> None:
    print(f"[patch] {msg}")


def copy_nanobot(src: Path, out: Path) -> None:
    if out.exists():
        log(f"removing existing {out}")
        shutil.rmtree(out)
    log(f"copying nanobot source {src} -> {out}")
    shutil.copytree(src, out, ignore=_ignore)


def copy_channel(out: Path) -> Path:
    dst = out / "nanobot" / "channels" / "deltachat"
    log(f"copying channel package {CHANNEL_SRC} -> {dst}")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(CHANNEL_SRC, dst, ignore=_ignore)
    return dst


def patch_pyproject(pyproject: Path) -> bool:
    text = pyproject.read_text(encoding="utf-8")
    marker = "dependencies = ["
    start = text.index(marker)
    close = text.index("\n]", start)

    existing = text[start:close]
    missing = []
    for req in DELTACHAT_REQUIREMENTS:
        name = req.split(">=")[0].split("<")[0].split("==")[0].split("[")[0].strip()
        if f'"{name}"' in existing or f"'{name}'" in existing:
            continue
        missing.append(req)

    if not missing:
        log("dependencies already present in pyproject.toml")
        return False

    insertion = "\n" + "\n".join(f'    "{req}",' for req in missing)
    patched = text[:close] + insertion + text[close:]
    pyproject.write_text(patched, encoding="utf-8")
    log(f"added dependencies: {', '.join(missing)}")
    return True


def install(out: Path) -> None:
    cmd = ["uv", "tool", "install", str(out)]
    log(" ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nanobot_src", type=Path, help="path to a nanobot checkout")
    parser.add_argument("dest", type=Path, help="output directory for the built fork")
    parser.add_argument("--install", action="store_true", help="run `uv tool install DEST` afterwards")
    args = parser.parse_args()

    if not CHANNEL_SRC.is_dir():
        log(f"channel package not found: {CHANNEL_SRC}")
        return 2

    src, out = args.nanobot_src, args.dest
    if not (src / "pyproject.toml").is_file():
        log(f"nanobot source not found at {src}")
        return 2

    copy_nanobot(src, out)
    copy_channel(out)
    patch_pyproject(out / "pyproject.toml")

    log(f"done. install with: uv tool install {out}")
    if args.install:
        install(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
