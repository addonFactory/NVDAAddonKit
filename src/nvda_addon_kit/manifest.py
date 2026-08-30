# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

from pathlib import Path

from .errors import BuildError
from .models import (
    MANIFEST_KEY_ORDER,
    Channel,
    AddonConfig,
    AddonMetadata,
    BrailleTable,
    DictionaryEntry,
    manifestQuoting,
)

_ALWAYS_EMITTED: frozenset[str] = frozenset(
    {
        "name",
        "summary",
        "author",
        "url",
        "version",
        "docFileName",
        "minimumNVDAVersion",
        "lastTestedNVDAVersion",
        "updateChannel",
    },
)

_OPTIONAL_KEYS: frozenset[str] = frozenset({"sourceURL", "license", "licenseURL"})

_TRANSLATED_KEYS: tuple[str, ...] = ("summary", "description", "changelog")


def _checkQuotable(key: str, value: str) -> None:
    quoting = manifestQuoting(key)
    if quoting and quoting in value:
        raise BuildError(
            f"[addon] {key} contains {quoting} , which would terminate its value early in "
            f"manifest.ini and produce a file NVDA cannot read. Remove or rephrase the quotes.",
        )


def _renderValue(key: str, value: str | None) -> str:
    if value is None:
        return "None"
    _checkQuotable(key, value)
    quoting = manifestQuoting(key)
    return f"{quoting}{value}{quoting}"


def _renderSection(
    sectionName: str,
    entries: dict[str, BrailleTable] | dict[str, DictionaryEntry],
    *,
    displayNamesOnly: bool = False,
    translate: dict[str, str] | None = None,
) -> str:
    lines = [f"\n[{sectionName}]"]
    for entryName, entry in entries.items():
        lines.append(f"[[{entryName}]]")
        for fieldName, fieldValue in vars(entry).items():
            if displayNamesOnly and fieldName != "displayName":
                continue
            if fieldName == "displayName" and translate is not None:
                fieldValue = translate.get(fieldValue, fieldValue)
            lines.append(f"{fieldName} = {fieldValue}")
    return "\n".join(lines) + "\n"


def _sections(
    config: AddonConfig,
) -> tuple[tuple[str, dict[str, BrailleTable] | dict[str, DictionaryEntry]], ...]:
    return (
        ("brailleTables", config.brailleTables),
        ("symbolDictionaries", config.symbolDictionaries),
        ("speechDictionaries", config.speechDictionaries),
    )


def renderManifest(config: AddonConfig, metadata: AddonMetadata | None = None) -> str:
    addon = metadata if metadata is not None else config.addon
    lines: list[str] = []

    for key in MANIFEST_KEY_ORDER:
        raw = getattr(addon, key)
        value: str | None = raw.manifestValue if isinstance(raw, Channel) else raw
        if key in _OPTIONAL_KEYS and not value:
            continue
        if key not in _ALWAYS_EMITTED and not value:
            continue
        lines.append(f"{key} = {_renderValue(key, value or None)}")

    manifest = "\n".join(lines) + "\n"
    for sectionName, entries in _sections(config):
        if entries:
            manifest += _renderSection(sectionName, entries)
    return manifest


def renderTranslatedManifest(
    config: AddonConfig,
    translations: dict[str, str],
    metadata: AddonMetadata | None = None,
) -> str:
    addon = metadata if metadata is not None else config.addon
    lines: list[str] = []

    for key in _TRANSLATED_KEYS:
        source: str = getattr(addon, key)
        if not source:
            continue
        translated = translations.get(source) or source
        lines.append(f"{key} = {_renderValue(key, translated)}")

    manifest = "\n".join(lines) + "\n"
    for sectionName, entries in _sections(config):
        if entries:
            manifest += _renderSection(sectionName, entries, displayNamesOnly=True, translate=translations)
    return manifest


def writeManifest(config: AddonConfig, metadata: AddonMetadata | None = None) -> Path:
    destination = config.addonDir / "manifest.ini"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(renderManifest(config, metadata), encoding="utf-8")
    return destination


def writeTranslatedManifest(
    config: AddonConfig,
    language: str,
    translations: dict[str, str],
    metadata: AddonMetadata | None = None,
) -> Path:
    destination = config.localeDir / language / "manifest.ini"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(renderTranslatedManifest(config, translations, metadata), encoding="utf-8")
    return destination
