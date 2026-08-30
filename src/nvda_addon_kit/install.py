# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

import os
import subprocess
import sys
from pathlib import Path

from .errors import InstallError
from .models import AddonConfig


def isWindows() -> bool:
    return sys.platform == "win32"


def addonsDirectory(nvdaPath: Path | None = None) -> Path:
    if nvdaPath is not None:
        portable = nvdaPath.expanduser().resolve()
        userConfig = portable / "userConfig"
        if not userConfig.is_dir():
            raise InstallError(
                f"{portable} does not look like a portable NVDA copy: it has no userConfig directory.",
            )
        return userConfig / "addons"

    appData = os.environ.get("APPDATA")
    if not appData:
        raise InstallError(
            "APPDATA is not set, so NVDA's configuration directory cannot be located. "
            "Pass --nvda-path to target a portable copy instead.",
        )
    return Path(appData) / "nvda" / "addons"


def _isLink(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        _ = os.readlink(path)
    except OSError:
        return False
    return True


def _removeLink(path: Path) -> None:
    try:
        path.unlink()
    except (OSError, PermissionError):
        try:
            path.rmdir()
        except OSError as exc:
            raise InstallError(f"Could not remove the existing link at {path}: {exc}") from exc


def _createJunction(link: Path, target: Path) -> None:
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout).strip()
        raise InstallError(
            f"Could not link {link} to {target}.\n"
            f"Creating a symbolic link needs Developer Mode or an elevated prompt, "
            f"and the junction fallback failed too: {message}",
        )


def linkAddon(config: AddonConfig, nvdaPath: Path | None = None) -> Path:
    if not isWindows():
        raise InstallError(
            "Linking an add-on into NVDA is only possible on Windows, where NVDA runs.",
        )

    target = config.addonDir.resolve()
    destination = addonsDirectory(nvdaPath) / config.addon.name
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists() or _isLink(destination):
        if not _isLink(destination):
            raise InstallError(
                f"{destination} is a real directory, which means {config.addon.name} is "
                f"already installed in NVDA. Uninstall it from NVDA's Add-on Store first, "
                f"so this does not delete an installed add-on and its settings.",
            )
        _removeLink(destination)

    try:
        os.symlink(target, destination, target_is_directory=True)
    except OSError:
        _createJunction(destination, target)

    return destination


def handOffToNVDA(bundle: Path) -> None:
    if not isWindows():
        raise InstallError(
            f"Installing requires Windows, where NVDA runs. The add-on was built "
            f"successfully at {bundle}; copy it to a Windows machine to install it.",
        )
    if not bundle.is_file():
        raise InstallError(f"{bundle} does not exist.")

    try:
        os.startfile(bundle)
    except OSError as exc:
        raise InstallError(
            f"Could not open {bundle.name} with NVDA: {exc}\n"
            f"NVDA must be running and registered as the handler for .nvda-addon files.",
        ) from exc
