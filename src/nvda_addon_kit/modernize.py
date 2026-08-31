# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

import shutil
import subprocess
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import tomlkit

from .config import CONFIG_FILENAME
from .errors import AddonKitError
from .migrate import convertBuildVars
from .scaffold import TEMPLATES_DIR


class Stage(StrEnum):
    CONFIG = "config"
    SCONS = "scons"
    CI = "ci"
    PROJECT = "project"
    IGNORE = "ignore"


class Change(StrEnum):
    CREATE = "create"
    REPLACE = "replace"
    EDIT = "edit"
    REMOVE = "remove"


BUILD_VARS = "buildVars.py"

SCONS_ARTEFACTS: tuple[str, ...] = (
    "sconstruct",
    "site_scons",
    "manifest.ini.tpl",
    "manifest-translated.ini.tpl",
    ".github/scripts/setOutputs.py",
)

CI_PAYLOAD: tuple[str, ...] = (".github/workflows/build_addon.yml",)

CROWDIN_PAYLOAD: tuple[str, ...] = (
    ".github/workflows/crowdinL10n.yml",
    ".github/scripts/crowdinSync.ps1",
    ".github/scripts/checkTranslation.py",
    ".github/scripts/languageMappings.json",
)

OBSOLETE_DEPENDENCIES: frozenset[str] = frozenset({"scons", "markdown"})

OBSOLETE_IGNORES: tuple[str, ...] = (".sconsign.dblite",)

STALE_REFERENCES: tuple[str, ...] = ("scons", "buildVars", "xgettext", "msgfmt")

REQUIRED_IGNORES: tuple[str, ...] = (
    "*.nvda-addon",
    "*.pot",
    "*.mo",
    "addon/manifest.ini",
    "addon/locale/*/manifest.ini",
    "addon/doc/*/*.html",
)


@dataclass(frozen=True)
class Action:
    change: Change
    path: Path
    detail: str
    content: str | None = None

    def describe(self, root: Path) -> str:
        try:
            shown = self.path.relative_to(root)
        except ValueError:
            shown = self.path
        return f"  {self.change.value:<8} {shown}  {self.detail}"


@dataclass(frozen=True)
class Plan:
    root: Path
    actions: list[Action] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.actions)


def _templatePath(relative: str) -> Path:
    inCi = relative.replace(".github/", "dot-github/", 1)
    return TEMPLATES_DIR / "ci" / inCi


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *arguments], cwd=root, capture_output=True, text=True, check=False)


def requireCleanTree(root: Path) -> None:
    if _git(root, "rev-parse", "--git-dir").returncode != 0:
        raise AddonKitError(
            f"{root} is not a git repository. Modernising rewrites several files, and without "
            f"git there is no way to review or undo it. Initialise a repository first, or pass "
            f"--allow-dirty to proceed anyway.",
        )

    status = _git(root, "status", "--porcelain")
    if status.returncode == 0 and status.stdout.strip():
        raise AddonKitError(
            "The working tree has uncommitted changes. Commit or stash them first, so the "
            "migration lands as one reviewable diff. Pass --allow-dirty to skip this check.",
        )


def _planConfig(root: Path, plan: list[Action], notes: list[str]) -> None:
    source = root / BUILD_VARS
    destination = root / CONFIG_FILENAME
    if not source.is_file():
        if not destination.is_file():
            notes.append(f"No {BUILD_VARS} and no {CONFIG_FILENAME}; nothing to convert.")
        return

    text, conversionNotes = convertBuildVars(source.read_text(encoding="utf-8"))
    notes.extend(conversionNotes)
    change = Change.REPLACE if destination.is_file() else Change.CREATE
    plan.append(Action(change, destination, f"from {BUILD_VARS}", text))
    plan.append(Action(Change.REMOVE, source, "replaced by addon.toml"))


def _planScons(root: Path, plan: list[Action], notes: list[str]) -> None:
    found = False
    for relative in SCONS_ARTEFACTS:
        path = root / relative
        if path.exists():
            found = True
            kind = "directory" if path.is_dir() else "file"
            plan.append(Action(Change.REMOVE, path, f"SCons build {kind}"))
    if not found:
        notes.append("No SCons build machinery found; the repository is already free of it.")


def _usesCrowdin(root: Path) -> bool:
    return any((root / relative).exists() for relative in CROWDIN_PAYLOAD)


def _planCi(root: Path, plan: list[Action], notes: list[str]) -> None:
    workflows = root / ".github" / "workflows"
    if not workflows.is_dir():
        notes.append("No .github/workflows directory; skipping CI.")
        return

    payload = CI_PAYLOAD + (CROWDIN_PAYLOAD if _usesCrowdin(root) else ())
    if not _usesCrowdin(root):
        notes.append("No Crowdin setup found; left the translation workflow out.")

    for relative in payload:
        target = root / relative
        template = _templatePath(relative)
        if not template.is_file() or not target.exists():
            continue
        content = template.read_text(encoding="utf-8")
        if target.read_text(encoding="utf-8") == content:
            continue
        plan.append(Action(Change.REPLACE, target, "calls nvaddon; no gettext install", content))

    unitTests = workflows / "unitTests.yml"
    if unitTests.is_file():
        notes.append("Left .github/workflows/unitTests.yml alone; it does not depend on SCons.")


def _rewritePyproject(text: str) -> tuple[str, list[str]]:
    document = tomlkit.parse(text)
    notes: list[str] = []

    groups = document.get("dependency-groups")
    if groups is not None:
        for groupName in list(groups.keys()):
            entries = groups[groupName]
            if not isinstance(entries, list):
                continue
            kept = [
                entry
                for entry in entries
                if not (
                    isinstance(entry, str)
                    and entry.split("=")[0].split("<")[0].split(">")[0].strip().lower()
                    in OBSOLETE_DEPENDENCIES
                )
            ]
            if len(kept) != len(entries):
                if groupName == "build" and not any("nvda-addon-kit" in str(e) for e in kept):
                    kept.append("nvda-addon-kit")
                groups[groupName] = kept
                notes.append(f"pyproject.toml: cleaned the [{groupName}] dependency group.")

    ruff = document.get("tool", {}).get("ruff") if "tool" in document else None
    if ruff is not None:
        include = ruff.get("include")
        if isinstance(include, list) and any("sconstruct" in str(item) for item in include):
            ruff["include"] = [item for item in include if "sconstruct" not in str(item)]
            notes.append("pyproject.toml: dropped sconstruct from [tool.ruff] include.")
        exclude = ruff.get("exclude")
        if isinstance(exclude, list) and any(BUILD_VARS in str(item) for item in exclude):
            ruff["exclude"] = [item for item in exclude if BUILD_VARS not in str(item)]
            notes.append("pyproject.toml: dropped buildVars.py from [tool.ruff] exclude.")
        perFile = ruff.get("lint", {}).get("per-file-ignores") if "lint" in ruff else None
        if perFile is not None and "sconstruct" in perFile:
            del perFile["sconstruct"]
            notes.append("pyproject.toml: dropped the sconstruct per-file ignore.")

    return tomlkit.dumps(document), notes


def _planRequirements(root: Path, plan: list[Action], notes: list[str]) -> None:
    path = root / "requirements.txt"
    if not path.is_file():
        return

    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [
        line
        for line in lines
        if line.split("=")[0].split("<")[0].split(">")[0].strip().lower() not in OBSOLETE_DEPENDENCIES
    ]
    if len(kept) == len(lines):
        return

    if not any(line.strip() for line in kept):
        plan.append(Action(Change.REMOVE, path, "only pinned the SCons toolchain"))
    else:
        if not any("nvda-addon-kit" in line for line in kept):
            kept.append("nvda-addon-kit")
        plan.append(Action(Change.EDIT, path, "SCons toolchain replaced", "\n".join(kept).strip() + "\n"))


def _planProject(root: Path, plan: list[Action], notes: list[str]) -> None:
    _planRequirements(root, plan, notes)

    path = root / "pyproject.toml"
    if not path.is_file():
        notes.append("No pyproject.toml; nothing to update.")
        return

    original = path.read_text(encoding="utf-8")
    try:
        rewritten, changes = _rewritePyproject(original)
    except Exception as exc:  # noqa: BLE001 - a hand-edited pyproject must not abort the plan
        notes.append(f"pyproject.toml could not be updated automatically ({exc}); update it by hand.")
        return

    if rewritten != original:
        plan.append(Action(Change.EDIT, path, f"{len(changes)} SCons references removed", rewritten))
        notes.extend(changes)


def _planIgnore(root: Path, plan: list[Action], notes: list[str]) -> None:
    path = root / ".gitignore"
    if not path.is_file():
        notes.append("No .gitignore; nothing to update.")
        return

    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if line.strip() not in OBSOLETE_IGNORES]
    removed = len(lines) - len(kept)

    existing = {line.strip() for line in kept}
    missing = [pattern for pattern in REQUIRED_IGNORES if pattern not in existing]
    if missing:
        kept = [*kept, "", *missing]

    if removed or missing:
        detail = []
        if removed:
            detail.append(f"dropped {removed} SCons entry")
        if missing:
            detail.append(f"added {len(missing)} build output")
        plan.append(Action(Change.EDIT, path, ", ".join(detail), "\n".join(kept).strip() + "\n"))


_PLANNERS = {
    Stage.CONFIG: _planConfig,
    Stage.SCONS: _planScons,
    Stage.CI: _planCi,
    Stage.PROJECT: _planProject,
    Stage.IGNORE: _planIgnore,
}


def _scanStaleReferences(root: Path, plan: list[Action], notes: list[str]) -> None:
    removing = {action.path for action in plan if action.change is Change.REMOVE}
    rewriting = {action.path for action in plan if action.change is not Change.REMOVE}

    searched = [
        *(root / ".github").rglob("*.yml"),
        *(root / ".github").rglob("*.yaml"),
        *(root / ".github").rglob("*.py"),
        *(root / ".github").rglob("*.ps1"),
    ]
    for path in sorted(searched):
        if path in removing or path in rewriting or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        hits = sorted({word for word in STALE_REFERENCES if word in text})
        if hits:
            notes.append(
                f"{path.relative_to(root)} still refers to {', '.join(hits)}; "
                f"it has custom steps, so update it by hand.",
            )


def planMigration(root: Path, stages: list[Stage] | None = None) -> Plan:
    actions: list[Action] = []
    notes: list[str] = []
    for stage in stages if stages is not None else list(Stage):
        _PLANNERS[stage](root, actions, notes)
    _scanStaleReferences(root, actions, notes)
    return Plan(root=root, actions=actions, notes=notes)


def applyMigration(plan: Plan) -> list[Action]:
    for action in plan.actions:
        match action.change:
            case Change.REMOVE:
                if action.path.is_dir():
                    shutil.rmtree(action.path)
                elif action.path.exists():
                    action.path.unlink()
            case _:
                if action.content is None:
                    continue
                action.path.parent.mkdir(parents=True, exist_ok=True)
                action.path.write_text(action.content, encoding="utf-8")
    return plan.actions


def copyTemplateAsset(relative: str, destination: Path) -> None:
    template = _templatePath(relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, destination)
