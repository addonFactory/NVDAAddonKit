# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.


import zipfile
from collections.abc import Iterable
from pathlib import Path

from .errors import BuildError

_ALWAYS_EXCLUDED: tuple[str, ...] = (
    "**/__pycache__/**",
    "**/*.py[co]",
    "**/.git/**",
    "**/.DS_Store",
    "**/*.orig",
    "**/*.rej",
    "**/*.po",
    "**/*.pot",
    "**/*.md",
)


def _isExcluded(relativePath: Path, patterns: Iterable[str]) -> bool:
    return any(relativePath.full_match(pattern) or relativePath.match(pattern) for pattern in patterns)


def createBundle(
    addonDir: Path,
    destination: Path,
    excludePatterns: Iterable[str] = (),
) -> Path:
    if not addonDir.is_dir():
        raise BuildError(f"Add-on directory {addonDir} does not exist.")

    manifest = addonDir / "manifest.ini"
    if not manifest.is_file():
        raise BuildError(
            f"{manifest} is missing, so the archive would not be a valid add-on. "
            f"This is generated during the build; run `nvaddon build`.",
        )

    patterns = (*_ALWAYS_EXCLUDED, *excludePatterns)
    base = addonDir.absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(base.rglob("*")):
            if path.is_dir():
                continue
            relativePath = path.relative_to(base)
            if _isExcluded(relativePath, patterns):
                continue
            archive.write(path, relativePath.as_posix())

    return destination


def listBundle(archivePath: Path) -> list[str]:
    with zipfile.ZipFile(archivePath) as archive:
        return sorted(archive.namelist())
