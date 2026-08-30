# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from .errors import AddonKitError
from .models import PLUGIN_DIRECTORIES, Answers

type Fallback = str | Callable[[], str]

_VALID_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

_FALLBACK_AUTHOR = "Your Name <you@example.com>"
_DEFAULT_MINIMUM_NVDA = "2024.1"
_DEFAULT_LAST_TESTED = "2025.3"
_PLUGIN_CHOICES: tuple[str, ...] = (*PLUGIN_DIRECTORIES, "none")

_NVDA_VERSION_NOTICE = (
    "\nNVDA compatibility. Check the versions you actually support at\n"
    "https://download.nvaccess.org/releases/ before publishing."
)


def _gitConfig(key: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "config", "--get", key],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _defaultAuthor() -> str:
    name = _gitConfig("user.name")
    email = _gitConfig("user.email")
    return f"{name} <{email}>" if name and email else name


def _defaultName(destination: Path) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_]", "", destination.resolve().name)
    if not candidate or not candidate[0].isalpha():
        return "myAddon"
    return candidate[0].lower() + candidate[1:]


def _ask(question: str, default: str = "", *, required: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        try:
            answer = input(f"{question}{suffix}: ").strip()
        except EOFError:
            if required and not default:
                raise AddonKitError(
                    f"No answer available for {question!r}. "
                    f"Pass the matching flag, or run without --yes to be prompted.",
                ) from None
            return default
        if answer:
            return answer
        if default or not required:
            return default
        print("  This one is required.")


def _askChoice(question: str, choices: tuple[str, ...], default: str) -> str:
    print(f"\n{question}")
    for index, choice in enumerate(choices, start=1):
        marker = " (default)" if choice == default else ""
        print(f"  {index}. {choice}{marker}")

    while True:
        answer = _ask("Choose a number or name", default)
        if answer in choices:
            return answer
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1]
        print(f"  Please enter a number from 1 to {len(choices)}, or one of: {', '.join(choices)}")


def _askYesNo(question: str, default: bool) -> bool:
    answer = _ask(f"{question} (yes/no)", "yes" if default else "no").lower()
    return answer.startswith("y")


def _validateName(name: str) -> str:
    if not _VALID_NAME.match(name):
        raise AddonKitError(
            f"{name!r} is not a usable add-on name. It becomes a Python module name, so it "
            f"must start with a letter and contain only letters, digits and underscores.",
        )
    return name


def collectAnswers(destination: Path, args: object) -> Answers:
    interactive = not getattr(args, "yes", False)

    def flag(attribute: str) -> str:
        return (getattr(args, attribute, None) or "").strip()

    def resolve(attribute: str, question: str, fallback: Fallback = "", *, required: bool = False) -> str:
        if answer := flag(attribute):
            return answer
        default = fallback() if callable(fallback) else fallback
        return _ask(question, default, required=required) if interactive else default

    if interactive:
        print("Creating a new NVDA add-on. Press Enter to accept the value in brackets.\n")

    name = _validateName(
        resolve("name", "Add-on name, internal to NVDA", lambda: _defaultName(destination), required=True),
    )
    summary = resolve("summary", "Summary, the name users see", name, required=True)
    description = resolve("description", "Description, shown in the add-on store", f"{summary} for NVDA.")
    author = resolve(
        "author",
        "Author, as Name <email>",
        lambda: _defaultAuthor() or _FALLBACK_AUTHOR,
        required=True,
    )
    version = resolve("addon_version", "Initial version, as major.minor.patch", Answers.version)
    url = resolve("url", "Documentation or homepage URL, if any")
    sourceURL = resolve("source_url", "Source repository URL, if any")
    license = resolve("license", "Licence", Answers.license)
    licenseURL = resolve("license_url", "Licence URL", Answers.licenseURL)

    if interactive and not flag("min_nvda"):
        print(_NVDA_VERSION_NOTICE)
    minimumNVDA = resolve("min_nvda", "Oldest NVDA version supported", _DEFAULT_MINIMUM_NVDA)
    lastTested = resolve("last_tested", "Most recent NVDA version tested", _DEFAULT_LAST_TESTED)

    baseLanguage = resolve("base_language", "Language the add-on is written in", Answers.baseLanguage)

    plugin = flag("plugin") or (
        _askChoice("Which starter plugin should be created?", _PLUGIN_CHOICES, Answers.plugin)
        if interactive
        else Answers.plugin
    )

    includeCI = not getattr(args, "no_ci", False)
    includeTooling = not getattr(args, "no_tooling", False)
    if interactive:
        if includeCI:
            includeCI = _askYesNo("Add GitHub workflows for building, releasing and translating?", True)
        if includeTooling:
            includeTooling = _askYesNo("Add the lint configuration?", True)

    return Answers(
        name=name,
        summary=summary,
        description=description,
        author=author,
        version=version,
        url=url,
        sourceURL=sourceURL,
        license=license,
        licenseURL=licenseURL,
        minimumNVDAVersion=minimumNVDA,
        lastTestedNVDAVersion=lastTested,
        baseLanguage=baseLanguage,
        plugin=plugin,
        includeCI=includeCI,
        includeTooling=includeTooling,
    )
