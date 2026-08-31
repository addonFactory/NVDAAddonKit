# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import tomlkit

from .errors import AddonKitError
from .models import Channel

_EXPLICIT_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_BUMP_PARTS: dict[str, int] = {"major": 0, "minor": 1, "patch": 2}


@dataclass(frozen=True)
class ReleasePlan:
    version: str
    channel: Channel
    tag: str
    changed: list[Path]
    pushed: bool


def nextVersion(current: str, bump: str) -> str:
    if _EXPLICIT_VERSION.match(bump):
        return bump

    if bump not in _BUMP_PARTS:
        raise AddonKitError(
            f"{bump!r} is not a version. Use major, minor, patch, or an explicit version such as 1.2.3.",
        )

    parts = current.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise AddonKitError(
            f"The current version {current!r} is not major.minor.patch, so it cannot be "
            f"bumped automatically. Pass an explicit version such as 1.0.0 instead.",
        )

    numbers = [int(part) for part in parts]
    index = _BUMP_PARTS[bump]
    numbers[index] += 1
    for lower in range(index + 1, 3):
        numbers[lower] = 0
    return ".".join(str(number) for number in numbers)


def tagName(version: str, channel: Channel, prefix: str = "") -> str:
    return f"{prefix}{version}-{channel.tagSuffix()}"


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *arguments], cwd=root, capture_output=True, text=True, check=False)


def _requireGit(root: Path, *arguments: str, failure: str) -> str:
    completed = _git(root, *arguments)
    if completed.returncode != 0:
        raise AddonKitError(f"{failure}: {(completed.stderr or completed.stdout).strip()}")
    return completed.stdout.strip()


def _currentBranch(root: Path) -> str:
    branch = _requireGit(
        root, "rev-parse", "--abbrev-ref", "HEAD", failure="Could not read the current branch"
    )
    if branch == "HEAD":
        raise AddonKitError(
            "HEAD is detached, so there is no branch to push. Check out a branch first.",
        )
    return branch


def _assertReleasable(root: Path, tag: str, *, push: bool) -> str:
    if _git(root, "rev-parse", "--git-dir").returncode != 0:
        raise AddonKitError(f"{root} is not a git repository, so there is nothing to release.")

    status = _git(root, "status", "--porcelain")
    if status.returncode == 0 and status.stdout.strip():
        raise AddonKitError(
            "The working tree has uncommitted changes. Commit or stash them first, so the "
            "release contains the version bump and nothing else.",
        )

    if _git(root, "rev-parse", "--verify", f"refs/tags/{tag}").returncode == 0:
        raise AddonKitError(f"Tag {tag} already exists locally. Delete it if you mean to move it.")

    if not push:
        return ""

    branch = _currentBranch(root)
    remote = _git(root, "config", "--get", f"branch.{branch}.remote")
    if remote.returncode != 0 or not remote.stdout.strip():
        raise AddonKitError(
            f"Branch {branch} has no upstream remote, so nothing can be pushed. "
            f"Set one with `git push -u origin {branch}`, or pass --no-push.",
        )
    remoteName = remote.stdout.strip()

    existing = _git(root, "ls-remote", "--tags", remoteName, f"refs/tags/{tag}")
    if existing.returncode != 0:
        raise AddonKitError(
            f"Could not reach the remote {remoteName!r} to check for tag {tag}: {existing.stderr.strip()}",
        )
    if existing.stdout.strip():
        raise AddonKitError(f"Tag {tag} already exists on {remoteName}. Releases are not overwritten.")

    return remoteName


def _updateChangelog(root: Path, version: str, channel: Channel) -> bool:
    changelog = root / "changelog.md"
    if not changelog.is_file():
        return False

    heading = f"## {version}" if channel is Channel.STABLE else f"## {version} ({channel})"
    lines = changelog.read_text(encoding="utf-8").splitlines()
    entry = [heading, "", "* ", ""]

    for index, line in enumerate(lines):
        if line.startswith("## "):
            lines[index:index] = entry
            break
    else:
        lines.extend(["", *entry])

    changelog.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def _writeConfig(configPath: Path, version: str, channel: Channel) -> None:
    document = tomlkit.parse(configPath.read_text(encoding="utf-8"))
    addon = document.get("addon")
    if addon is None:
        raise AddonKitError(f"{configPath} has no [addon] table.")
    addon["version"] = version
    addon["updateChannel"] = channel.value
    configPath.write_text(tomlkit.dumps(document), encoding="utf-8")


def _rollback(root: Path, tag: str, originalHead: str) -> None:
    _git(root, "tag", "-d", tag)
    _git(root, "reset", "--hard", originalHead)


def release(
    configPath: Path,
    version: str,
    channel: Channel,
    *,
    push: bool = True,
    changelog: bool = False,
    tagPrefix: str = "",
) -> ReleasePlan:
    document = tomlkit.parse(configPath.read_text(encoding="utf-8"))
    addon = document.get("addon")
    if addon is None:
        raise AddonKitError(f"{configPath} has no [addon] table.")

    root = configPath.parent
    newVersion = nextVersion(str(addon.get("version", "")), version)
    tag = tagName(newVersion, channel, tagPrefix)

    if changelog and not (root / "changelog.md").is_file():
        raise AddonKitError(f"No changelog.md in {root}, so --changelog has nothing to update.")

    remote = _assertReleasable(root, tag, push=push)
    branch = _currentBranch(root) if push else ""
    originalHead = _requireGit(root, "rev-parse", "HEAD", failure="Could not read HEAD")

    _writeConfig(configPath, newVersion, channel)
    changed = [configPath]
    if changelog and _updateChangelog(root, newVersion, channel):
        changed.append(root / "changelog.md")

    relative = [str(path.relative_to(root)) for path in changed]
    try:
        _requireGit(root, "add", *relative, failure="Could not stage the release")
        _requireGit(root, "commit", "-m", f"Release {tag}", failure="Could not commit the release")
        _requireGit(root, "tag", "-a", tag, "-m", f"Release {tag}", failure=f"Could not create tag {tag}")

        if push:
            _requireGit(
                root,
                "push",
                "--atomic",
                remote,
                branch,
                f"refs/tags/{tag}",
                failure="Could not push the release",
            )
    except AddonKitError:
        _rollback(root, tag, originalHead)
        raise

    return ReleasePlan(version=newVersion, channel=channel, tag=tag, changed=changed, pushed=push)
