# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

from dataclasses import dataclass


class AddonKitError(Exception):
    pass


class ConfigError(AddonKitError):
    pass


class ConfigNotFoundError(ConfigError):
    pass


class BuildError(AddonKitError):
    pass


class LocaleError(AddonKitError):
    pass


class InstallError(AddonKitError):
    pass


@dataclass(frozen=True)
class ValidationIssue:
    level: str
    message: str
    location: str = ""

    def __str__(self) -> str:
        prefix = f"{self.location}: " if self.location else ""
        return f"{self.level}: {prefix}{self.message}"
