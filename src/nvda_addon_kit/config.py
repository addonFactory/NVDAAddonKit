# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

import re
import tomllib
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.items import Comment, Whitespace

from .errors import ConfigError, ConfigNotFoundError, ValidationIssue
from .models import (
    TRANSLATABLE_METADATA_KEYS,
    AddonConfig,
    AddonMetadata,
    BrailleTable,
    BuildConfig,
    Channel,
    DictionaryEntry,
    DocsConfig,
    L10nConfig,
    ReleaseConfig,
    TranslatableString,
)

CONFIG_FILENAME = "addon.toml"

_NESTED_TABLES: dict[str, type[BrailleTable] | type[DictionaryEntry]] = {
    "brailleTables": BrailleTable,
    "symbolDictionaries": DictionaryEntry,
    "speechDictionaries": DictionaryEntry,
}

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
_KEY_LINE = re.compile(r"""^\s*(?P<key>[A-Za-z0-9_-]+|"[^"]*"|'[^']*')\s*=(?P<rest>.*)$""")
_TABLE_LINE = re.compile(r"^\s*\[\[?(?P<path>.*?)\]\]?\s*(?:#.*)?$")


def _quoteSegment(segment: str) -> str:
    return segment if _BARE_KEY.match(segment) else f'"{segment}"'


def joinKeyPath(*segments: str) -> str:
    return ".".join(_quoteSegment(s) for s in segments)


def _splitDottedKey(text: str) -> list[str]:
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for char in text:
        if quote:
            if char == quote:
                quote = None
            else:
                current.append(char)
        elif char in "\"'":
            quote = char
        elif char == ".":
            segments.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    segments.append("".join(current).strip())
    return [s for s in segments if s]


def _opensMultilineString(rest: str) -> str | None:
    for delimiter in ('"""', "'''"):
        if rest.count(delimiter) % 2 == 1:
            return delimiter
    return None


def _scanKeyLines(source: str) -> dict[str, int]:
    lines: dict[str, int] = {}
    table: list[str] = []
    openDelimiter: str | None = None

    for lineno, line in enumerate(source.splitlines(), start=1):
        if openDelimiter is not None:
            if openDelimiter in line:
                openDelimiter = None
            continue

        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if tableMatch := _TABLE_LINE.match(line):
            table = _splitDottedKey(tableMatch.group("path"))
            continue

        if keyMatch := _KEY_LINE.match(line):
            key = keyMatch.group("key").strip("\"'")
            path = joinKeyPath(*table, key) if table else joinKeyPath(key)
            lines.setdefault(path, lineno)
            openDelimiter = _opensMultilineString(keyMatch.group("rest"))

    return lines


def _commentsForTable(container: Any) -> dict[str, str]:
    comments: dict[str, str] = {}
    pending: list[str] = []

    for key, item in container.body:
        if key is None:
            if isinstance(item, Comment):
                text = item.trivia.comment.lstrip("#")
                pending.append(text.removeprefix(" "))
            elif isinstance(item, Whitespace) and "\n" in item.value:
                pending.clear()
            continue

        leading = getattr(item.trivia, "comment", "")
        if leading and not pending:
            text = leading.lstrip("#")
            pending.append(text.removeprefix(" "))

        if pending:
            comments[key.key] = "\n".join(pending)
            pending.clear()

    return comments


def _collectTranslatables(source: str, data: dict[str, Any]) -> list[TranslatableString]:
    keyLines = _scanKeyLines(source)
    try:
        document = tomlkit.parse(source)
    except Exception as exc:
        raise ConfigError(f"{CONFIG_FILENAME}: {exc}") from exc

    translatables: list[TranslatableString] = []

    addonTable = document.get("addon")
    addonComments = _commentsForTable(addonTable.value) if addonTable is not None else {}
    addonData = data.get("addon", {})
    for key in TRANSLATABLE_METADATA_KEYS:
        message = addonData.get(key)
        if not message:
            continue
        path = joinKeyPath("addon", key)
        translatables.append(
            TranslatableString(
                keyPath=path,
                message=str(message),
                lineno=keyLines.get(path, 0),
                comment=addonComments.get(key),
            ),
        )

    for tableName in _NESTED_TABLES:
        entries = data.get(tableName)
        if not isinstance(entries, dict):
            continue
        tableItem = document.get(tableName)
        for entryName, entryData in entries.items():
            displayName = entryData.get("displayName") if isinstance(entryData, dict) else None
            if not displayName:
                continue
            comment = None
            if tableItem is not None and entryName in tableItem:
                comment = _commentsForTable(tableItem[entryName].value).get("displayName")
            path = joinKeyPath(tableName, entryName, "displayName")
            translatables.append(
                TranslatableString(
                    keyPath=path,
                    message=str(displayName),
                    lineno=keyLines.get(path, 0),
                    comment=comment,
                ),
            )

    return translatables


def _requireStr(table: dict[str, Any], key: str, tableName: str) -> str:
    value = table.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ConfigError(f"{CONFIG_FILENAME}: [{tableName}] is missing the required key `{key}`")
    if not isinstance(value, str):
        raise ConfigError(
            f"{CONFIG_FILENAME}: [{tableName}] `{key}` must be a string, got {type(value).__name__}"
        )
    return value


def _optionalStr(table: dict[str, Any], key: str, tableName: str) -> str | None:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(
            f"{CONFIG_FILENAME}: [{tableName}] `{key}` must be a string, got {type(value).__name__}"
        )
    return value or None


def _strList(table: dict[str, Any], key: str, tableName: str) -> list[str]:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{CONFIG_FILENAME}: [{tableName}] `{key}` must be a list of strings")
    return list(value)


def _bool(table: dict[str, Any], key: str, default: bool, location: str) -> bool:
    value = table.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{CONFIG_FILENAME}: {location} `{key}` must be true or false")
    return value


def _parseNested(data: dict[str, Any], tableName: str) -> dict[str, Any]:
    entries = data.get(tableName, {})
    if not isinstance(entries, dict):
        raise ConfigError(f"{CONFIG_FILENAME}: [{tableName}] must be a table")

    model = _NESTED_TABLES[tableName]
    parsed: dict[str, Any] = {}
    for entryName, entryData in entries.items():
        location = f'[{tableName}."{entryName}"]'
        if not isinstance(entryData, dict):
            raise ConfigError(f"{CONFIG_FILENAME}: {location} must be a table")
        displayName = _requireStr(entryData, "displayName", f'{tableName}."{entryName}"')
        if model is BrailleTable:
            parsed[entryName] = BrailleTable(
                displayName=displayName,
                contracted=_bool(entryData, "contracted", False, location),
                output=_bool(entryData, "output", True, location),
                input=_bool(entryData, "input", True, location),
            )
        else:
            parsed[entryName] = DictionaryEntry(
                displayName=displayName,
                mandatory=_bool(entryData, "mandatory", False, location),
            )
    return parsed


def _channel(table: dict[str, Any]) -> Channel:
    try:
        return Channel.parse(_optionalStr(table, "updateChannel", "addon"))
    except ValueError as exc:
        raise ConfigError(f"{CONFIG_FILENAME}: [addon] {exc}") from exc


def parse(source: str, root: Path) -> AddonConfig:
    try:
        data = tomllib.loads(source)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{CONFIG_FILENAME}: {exc}") from exc

    addonData = data.get("addon")
    if not isinstance(addonData, dict):
        raise ConfigError(f"{CONFIG_FILENAME}: missing the required [addon] table")

    buildData = data.get("build", {})
    l10nData = data.get("l10n", {})
    docsData = data.get("docs", {})
    releaseData = data.get("release", {})
    for name, table in (
        ("build", buildData),
        ("l10n", l10nData),
        ("docs", docsData),
        ("release", releaseData),
    ):
        if not isinstance(table, dict):
            raise ConfigError(f"{CONFIG_FILENAME}: [{name}] must be a table")

    metadata = AddonMetadata(
        name=_requireStr(addonData, "name", "addon"),
        summary=_requireStr(addonData, "summary", "addon"),
        version=_requireStr(addonData, "version", "addon"),
        author=_requireStr(addonData, "author", "addon"),
        description=_optionalStr(addonData, "description", "addon") or "",
        changelog=_optionalStr(addonData, "changelog", "addon") or "",
        url=_optionalStr(addonData, "url", "addon"),
        sourceURL=_optionalStr(addonData, "sourceURL", "addon"),
        docFileName=_optionalStr(addonData, "docFileName", "addon") or "readme.html",
        minimumNVDAVersion=_optionalStr(addonData, "minimumNVDAVersion", "addon"),
        lastTestedNVDAVersion=_optionalStr(addonData, "lastTestedNVDAVersion", "addon"),
        updateChannel=_channel(addonData),
        license=_optionalStr(addonData, "license", "addon"),
        licenseURL=_optionalStr(addonData, "licenseURL", "addon"),
    )

    build = BuildConfig(
        pythonSources=_strList(buildData, "pythonSources", "build"),
        excludedFiles=_strList(buildData, "excludedFiles", "build"),
        addonPath=_optionalStr(buildData, "addonPath", "build") or "addon",
    )
    l10n = L10nConfig(
        baseLanguage=_optionalStr(l10nData, "baseLanguage", "l10n") or "en",
        extraSources=_strList(l10nData, "extraSources", "l10n"),
        msgidBugsAddress=(_optionalStr(l10nData, "msgidBugsAddress", "l10n") or L10nConfig.msgidBugsAddress),
    )
    docs = DocsConfig(markdownExtensions=_strList(docsData, "markdownExtensions", "docs"))
    release = ReleaseConfig(tagPrefix=_optionalStr(releaseData, "tagPrefix", "release") or "")

    return AddonConfig(
        addon=metadata,
        build=build,
        l10n=l10n,
        docs=docs,
        release=release,
        brailleTables=_parseNested(data, "brailleTables"),
        symbolDictionaries=_parseNested(data, "symbolDictionaries"),
        speechDictionaries=_parseNested(data, "speechDictionaries"),
        translatables=_collectTranslatables(source, data),
        root=root,
    )


def findConfig(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        path = candidate / CONFIG_FILENAME
        if path.is_file():
            return path
    raise ConfigNotFoundError(
        f"No {CONFIG_FILENAME} found in {current} or any parent directory.\n"
        f"Run `nvaddon init` to create an add-on here, "
        f"or `nvaddon migrate` to convert an existing buildVars.py.",
    )


def load(start: Path | None = None) -> AddonConfig:
    path = findConfig(start)
    return parse(path.read_text(encoding="utf-8"), path.parent)


_STORE_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_NVDA_VERSION = re.compile(r"^\d{4}\.\d+(\.\d+)?$")


def _nvdaVersionKey(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def validate(config: AddonConfig) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    addon = config.addon

    def report(level: str, message: str, location: str = f"{CONFIG_FILENAME}: [addon]") -> None:
        issues.append(ValidationIssue(level, message, location))

    def key(name: str) -> str:
        return f"{CONFIG_FILENAME}: [addon] {name}"

    if not _STORE_VERSION.match(addon.version):
        report(
            "error",
            f"version {addon.version!r} must be major.minor.patch integers "
            f"to be accepted by the NVDA add-on store",
            key("version"),
        )

    for name in ("minimumNVDAVersion", "lastTestedNVDAVersion"):
        value: str | None = getattr(addon, name)
        if value is None:
            report(
                "warning",
                f"{name} is not set; NVDA cannot check compatibility and the "
                f"add-on store will reject the submission",
                key(name),
            )
        elif not _NVDA_VERSION.match(value):
            report("error", f"{name} {value!r} is not a valid NVDA version such as '2024.1'", key(name))

    minimum, lastTested = addon.minimumNVDAVersion, addon.lastTestedNVDAVersion
    if (
        minimum
        and lastTested
        and _NVDA_VERSION.match(minimum)
        and _NVDA_VERSION.match(lastTested)
        and _nvdaVersionKey(minimum) > _nvdaVersionKey(lastTested)
    ):
        report(
            "error",
            f"minimumNVDAVersion ({minimum}) is newer than lastTestedNVDAVersion ({lastTested})",
        )

    if not config.addonDir.is_dir():
        report(
            "error",
            f"add-on directory {config.build.addonPath!r} does not exist",
            str(config.addonDir),
        )

    if not config.build.pythonSources:
        report(
            "warning",
            "build.pythonSources is empty, so no Python source will be scanned for translatable strings",
            f"{CONFIG_FILENAME}: [build] pythonSources",
        )

    docFile = addon.docFileName
    if docFile and docFile.endswith(".html"):
        markdownSource = config.root / f"{Path(docFile).stem}.md"
        if not markdownSource.is_file():
            report(
                "warning",
                f"docFileName is {docFile!r} but {markdownSource.name} does not exist, "
                f"so the Help button will not work",
                str(markdownSource),
            )

    baseLanguage = config.l10n.baseLanguage
    if config.localeDir.is_dir() and (config.localeDir / baseLanguage).is_dir():
        report(
            "warning",
            f"locale/{baseLanguage} exists, but {baseLanguage} is the base language "
            f"and is never translated; NVDA will ignore it",
            str(config.localeDir / baseLanguage),
        )

    return issues
