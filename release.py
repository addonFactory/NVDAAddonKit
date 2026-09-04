# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

import argparse
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent
PYPROJECT = ROOT / "pyproject.toml"

VERSION = re.compile(r"^\d+\.\d+\.\d+$")


class ReleaseError(Exception):
    pass


def git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, text=True, check=False)


def requireGit(*arguments: str, failure: str) -> str:
    completed = git(*arguments)
    if completed.returncode != 0:
        raise ReleaseError(f"{failure}: {(completed.stderr or completed.stdout).strip()}")
    return completed.stdout.strip()


def currentVersion() -> str:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    if not version:
        raise ReleaseError(f"{PYPROJECT} has no [project] version.")
    return str(version)


def requireVersion(requested: str) -> str:
    if not VERSION.match(requested):
        raise ReleaseError(
            f"{requested!r} is not a version number. Pass the version to release "
            f"as major.minor.patch.\n"
            f"  python release.py 1.2.3",
        )
    return requested


def currentBranch() -> str:
    branch = requireGit("rev-parse", "--abbrev-ref", "HEAD", failure="Could not read the branch")
    if branch == "HEAD":
        raise ReleaseError("HEAD is detached, so there is no branch to push.")
    return branch


def assertReleasable(tag: str, *, push: bool) -> str:
    if git("rev-parse", "--git-dir").returncode != 0:
        raise ReleaseError(f"{ROOT} is not a git repository.")

    status = git("status", "--porcelain")
    if status.returncode == 0 and status.stdout.strip():
        raise ReleaseError(
            "The working tree has uncommitted changes. Commit or stash them first, so the "
            "release contains the version bump and nothing else.",
        )

    if git("rev-parse", "--verify", f"refs/tags/{tag}").returncode == 0:
        raise ReleaseError(f"Tag {tag} already exists locally.")

    if not push:
        return ""

    branch = currentBranch()
    remote = git("config", "--get", f"branch.{branch}.remote")
    if remote.returncode != 0 or not remote.stdout.strip():
        raise ReleaseError(
            f"Branch {branch} has no upstream remote. Set one with "
            f"`git push -u origin {branch}`, or pass --no-push.",
        )
    remoteName = remote.stdout.strip()

    existing = git("ls-remote", "--tags", remoteName, f"refs/tags/{tag}")
    if existing.returncode != 0:
        raise ReleaseError(f"Could not reach {remoteName!r}: {existing.stderr.strip()}")
    if existing.stdout.strip():
        raise ReleaseError(f"Tag {tag} already exists on {remoteName}.")

    return remoteName


def writeVersion(version: str) -> None:
    lines = PYPROJECT.read_text(encoding="utf-8").splitlines(keepends=True)
    inProject = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("["):
            if inProject:
                break
            inProject = stripped == "[project]"
            continue
        if inProject and re.match(r"^version\s*=", stripped):
            lines[index] = re.sub(r'"[^"]*"', f'"{version}"', line, count=1)
            PYPROJECT.write_text("".join(lines), encoding="utf-8")
            return
    raise ReleaseError(f"Could not find the version line in [project] of {PYPROJECT}.")


def relock() -> bool:
    uv = shutil.which("uv")
    if uv is None:
        return False
    completed = subprocess.run([uv, "lock"], cwd=ROOT, capture_output=True, text=True, check=False)
    return completed.returncode == 0


def confirm(current: str, new: str, tag: str, push: bool) -> bool:
    print(f"current version: {current}")
    print(f"version to be released: {new}")
    print(f"tag: {tag}")
    print(f"push: {'yes' if push else 'no (--no-push)'}")
    print()

    try:
        answer = input("Release? [Y/n]: ").strip().lower()
    except EOFError:
        raise ReleaseError(
            "No answer available; nothing was released. Pass -y to release without confirming.",
        ) from None
    return answer in ("", "y", "yes")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="release.py",
        description="Release nvda-addon-kit: bump the version, commit, tag and push.",
    )
    parser.add_argument("version", help="the version to release, as major.minor.patch")
    parser.add_argument("--no-push", action="store_true", help="commit and tag without pushing")
    parser.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    args = parser.parse_args(argv)

    try:
        current = currentVersion()
        new = requireVersion(args.version)
        tag = f"v{new}"
        message = f"release NVDAAddonKit v{new}"

        remote = assertReleasable(tag, push=not args.no_push)
        branch = currentBranch() if not args.no_push else ""

        if not args.yes and not confirm(current, new, tag, not args.no_push):
            print("Cancelled; nothing was changed.")
            return 1

        originalHead = requireGit("rev-parse", "HEAD", failure="Could not read HEAD")
        writeVersion(new)
        changed = ["pyproject.toml"]
        if relock():
            changed.append("uv.lock")
        else:
            print("warning: uv not found, so uv.lock was not refreshed.", file=sys.stderr)

        try:
            requireGit("add", *changed, failure="Could not stage the release")
            requireGit("commit", "-m", message, failure="Could not commit the release")
            requireGit("tag", "-a", tag, "-m", message, failure=f"Could not create tag {tag}")
            if not args.no_push:
                requireGit(
                    "push",
                    "--atomic",
                    remote,
                    branch,
                    f"refs/tags/{tag}",
                    failure="Could not push the release",
                )
        except ReleaseError:
            git("tag", "-d", tag)
            git("reset", "--hard", originalHead)
            raise
    except ReleaseError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"\n{current} -> {new}")
    print(f"Committed and tagged {tag}")
    if args.no_push:
        print("Not pushed. When you are ready:")
        print(f"  git push --atomic origin HEAD refs/tags/{tag}")
    else:
        print("Pushed the commit and the tag together.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
