# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Channel(StrEnum):
    STABLE = "stable"
    BETA = "beta"
    DEV = "dev"

    @classmethod
    def parse(cls, value: str | None) -> "Channel":
        if not value:
            return cls.STABLE
        try:
            return cls(value.strip().lower())
        except ValueError:
            raise ValueError(
                f"{value!r} is not an update channel. Use one of: "
                f"{', '.join(member.value for member in cls)}.",
            ) from None

    @property
    def manifestValue(self) -> str | None:
        return None if self is Channel.STABLE else self.value

    def tagSuffix(self) -> str:
        return self.value


TRANSLATABLE_METADATA_KEYS: tuple[str, ...] = ("summary", "description", "changelog")

MANIFEST_KEY_ORDER: tuple[str, ...] = (
    "name",
    "summary",
    "description",
    "author",
    "url",
    "version",
    "changelog",
    "docFileName",
    "minimumNVDAVersion",
    "lastTestedNVDAVersion",
    "updateChannel",
    "sourceURL",
    "license",
    "licenseURL",
)

_QUOTED_KEYS: frozenset[str] = frozenset({"summary", "author"})
_BLOCK_QUOTED_KEYS: frozenset[str] = frozenset({"description", "changelog"})


def manifestQuoting(key: str) -> str:
    if key in _BLOCK_QUOTED_KEYS:
        return '"""'
    if key in _QUOTED_KEYS:
        return '"'
    return ""


PLUGIN_DIRECTORIES: dict[str, str] = {
    "globalPlugin": "globalPlugins",
    "appModule": "appModules",
    "synthDriver": "synthDrivers",
    "brailleDisplayDriver": "brailleDisplayDrivers",
    "visionEnhancementProvider": "visionEnhancementProviders",
}


@dataclass
class Answers:
    name: str
    summary: str
    description: str
    author: str
    version: str = "1.0.0"
    changelog: str = "Initial release."
    url: str = ""
    sourceURL: str = ""
    license: str = "GPL v2"
    licenseURL: str = "https://www.gnu.org/licenses/old-licenses/gpl-2.0.html"
    minimumNVDAVersion: str = ""
    lastTestedNVDAVersion: str = ""
    baseLanguage: str = "en"
    plugin: str = "globalPlugin"
    includeCI: bool = True
    includeTooling: bool = True

    def pythonSources(self) -> str:
        directory = PLUGIN_DIRECTORIES.get(self.plugin)
        pattern = f"addon/{directory}/**/*.py" if directory else "addon/**/*.py"
        return f'["{pattern}"]'

    def placeholders(self) -> dict[str, str]:
        return {
            "NAME": self.name,
            "SUMMARY": self.summary,
            "DESCRIPTION": self.description,
            "CHANGELOG": self.changelog,
            "VERSION": self.version,
            "AUTHOR": self.author,
            "URL": self.url,
            "SOURCE_URL": self.sourceURL,
            "LICENSE": self.license,
            "LICENSE_URL": self.licenseURL,
            "MIN_NVDA": self.minimumNVDAVersion,
            "LAST_TESTED": self.lastTestedNVDAVersion,
            "BASE_LANGUAGE": self.baseLanguage,
            "PYTHON_SOURCES": self.pythonSources(),
        }


@dataclass(frozen=True)
class TranslatableString:
    keyPath: str
    message: str
    lineno: int
    comment: str | None = None


@dataclass(frozen=True)
class AddonMetadata:
    name: str
    summary: str
    version: str
    author: str
    description: str = ""
    changelog: str = ""
    url: str | None = None
    sourceURL: str | None = None
    docFileName: str = "readme.html"
    minimumNVDAVersion: str | None = None
    lastTestedNVDAVersion: str | None = None
    updateChannel: Channel = Channel.STABLE
    license: str | None = None
    licenseURL: str | None = None


@dataclass(frozen=True)
class BuildConfig:
    pythonSources: list[str] = field(default_factory=list)
    excludedFiles: list[str] = field(default_factory=list)
    addonPath: str = "addon"


@dataclass(frozen=True)
class L10nConfig:
    baseLanguage: str = "en"
    extraSources: list[str] = field(default_factory=list)
    msgidBugsAddress: str = "nvda-translations@groups.io"


@dataclass(frozen=True)
class ReleaseConfig:
    tagPrefix: str = "v"


@dataclass(frozen=True)
class DocsConfig:
    markdownExtensions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BrailleTable:
    displayName: str
    contracted: bool = False
    output: bool = True
    input: bool = True


@dataclass(frozen=True)
class DictionaryEntry:
    displayName: str
    mandatory: bool = False


@dataclass(frozen=True)
class AddonConfig:
    addon: AddonMetadata
    build: BuildConfig
    l10n: L10nConfig
    docs: DocsConfig
    release: ReleaseConfig = field(default_factory=ReleaseConfig)
    brailleTables: dict[str, BrailleTable] = field(default_factory=dict)
    symbolDictionaries: dict[str, DictionaryEntry] = field(default_factory=dict)
    speechDictionaries: dict[str, DictionaryEntry] = field(default_factory=dict)
    translatables: list[TranslatableString] = field(default_factory=list)
    root: Path = field(default_factory=Path)

    @property
    def addonDir(self) -> Path:
        return self.root / self.build.addonPath

    @property
    def localeDir(self) -> Path:
        return self.addonDir / "locale"

    @property
    def docsDir(self) -> Path:
        return self.addonDir / "doc"

    @property
    def potPath(self) -> Path:
        return self.root / f"{self.addon.name}.pot"

    def bundleName(self) -> str:
        return f"{self.addon.name}-{self.addon.version}.nvda-addon"
