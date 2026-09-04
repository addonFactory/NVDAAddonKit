# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

import shutil
from pathlib import Path

from .errors import AddonKitError
from .files import writeText
from .models import PLUGIN_DIRECTORIES, Answers
from .wizard import collectAnswers

TEMPLATES_DIR = Path(__file__).parent / "templates"

_RAW_PLACEHOLDERS: frozenset[str] = frozenset({"PYTHON_SOURCES"})

_BLOCK_PLACEHOLDERS: frozenset[str] = frozenset({"DESCRIPTION", "CHANGELOG"})


def _escapeToml(value: str, block: bool) -> str:
    escaped = value.replace("\\", "\\\\")
    if block:
        return escaped.replace('"""', '\\"\\"\\"')
    return escaped.replace('"', '\\"').replace("\n", "\\n")


def _escapePython(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _substitute(text: str, placeholders: dict[str, str], suffix: str) -> str:
    for key, value in placeholders.items():
        marker = f"%%{key}%%"
        if marker not in text:
            continue
        if key in _RAW_PLACEHOLDERS:
            replacement = value
        elif suffix == ".toml":
            replacement = _escapeToml(value, block=key in _BLOCK_PLACEHOLDERS)
        elif suffix == ".py":
            replacement = _escapePython(value)
        else:
            replacement = value
        text = text.replace(marker, replacement)
    return text


def _destinationName(name: str) -> str:
    return f".{name[len('dot-') :]}" if name.startswith("dot-") else name


def _copyTree(source: Path, destination: Path, placeholders: dict[str, str]) -> list[Path]:
    written: list[Path] = []

    for path in sorted(source.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(source)
        target = destination.joinpath(*(_destinationName(part) for part in relative.parts))
        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            _ = shutil.copyfile(path, target)
        else:
            writeText(target, _substitute(text, placeholders, target.suffix))
        written.append(target)

    return written


def _writePlugin(destination: Path, answers: Answers, placeholders: dict[str, str]) -> list[Path]:
    directory = PLUGIN_DIRECTORIES.get(answers.plugin)
    if directory is None:
        return []

    source = TEMPLATES_DIR / "plugin" / f"{answers.plugin}.py"
    target = destination / "addon" / directory / f"{answers.name}.py"
    writeText(target, _substitute(source.read_text(encoding="utf-8"), placeholders, ".py"))
    return [target]


def _isEffectivelyEmpty(directory: Path) -> bool:
    if not directory.exists():
        return True
    return all(entry.name == ".git" for entry in directory.iterdir())


def initialiseAddon(destination: Path, args: object) -> list[Path]:
    answers = collectAnswers(destination, args)

    if not _isEffectivelyEmpty(destination) and not getattr(args, "force", False):
        raise AddonKitError(
            f"{destination} is not empty. Pass --force to write into it anyway, "
            f"or choose an empty directory.",
        )

    destination.mkdir(parents=True, exist_ok=True)
    placeholders = answers.placeholders()
    written: list[Path] = []

    written += _copyTree(TEMPLATES_DIR / "core", destination, placeholders)
    written += _writePlugin(destination, answers, placeholders)

    if answers.includeCI:
        written += _copyTree(TEMPLATES_DIR / "ci", destination, placeholders)
    if answers.includeTooling:
        written += _copyTree(TEMPLATES_DIR / "tooling", destination, placeholders)

    (destination / "addon" / "locale").mkdir(parents=True, exist_ok=True)

    return sorted(written)
