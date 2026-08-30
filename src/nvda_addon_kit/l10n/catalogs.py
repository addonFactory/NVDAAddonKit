# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

from pathlib import Path

from babel.core import Locale, UnknownLocaleError
from babel.messages.catalog import Catalog
from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po, write_po

from ..errors import LocaleError
from ..models import AddonConfig
from .extract import buildCatalog

DOMAIN = "nvda"


def poPath(config: AddonConfig, language: str) -> Path:
    return config.localeDir / language / "LC_MESSAGES" / f"{DOMAIN}.po"


def moPath(config: AddonConfig, language: str) -> Path:
    return config.localeDir / language / "LC_MESSAGES" / f"{DOMAIN}.mo"


def discoverLocales(config: AddonConfig) -> list[str]:
    if not config.localeDir.is_dir():
        return []
    return sorted(
        entry.name
        for entry in config.localeDir.iterdir()
        if entry.is_dir() and poPath(config, entry.name).is_file()
    )


def _parseLocale(language: str) -> Locale:
    try:
        return Locale.parse(language)
    except (UnknownLocaleError, ValueError) as exc:
        raise LocaleError(
            f"{language!r} is not a recognised language code. Use a code such as 'de', 'pt_BR' or 'sr_Latn'.",
        ) from exc


def _writeCatalog(target: Path, catalog: Catalog, **options: bool) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as poFile:
        write_po(poFile, catalog, sort_by_file=True, **options)
    return target


def _readCatalog(config: AddonConfig, language: str) -> Catalog:
    source = poPath(config, language)
    try:
        with source.open("rb") as poFile:
            return read_po(poFile, locale=language, domain=DOMAIN)
    except OSError as exc:
        raise LocaleError(f"Could not read {source}: {exc}") from exc


def writePot(config: AddonConfig, *, merge: bool = False, destination: Path | None = None) -> Path:
    catalog = buildCatalog(config)
    return _writeCatalog(destination or config.potPath, catalog, omit_header=merge, no_location=merge)


def addLocales(config: AddonConfig, languages: list[str]) -> list[Path]:
    created: list[Path] = []

    for language in languages:
        locale = _parseLocale(language)
        target = poPath(config, language)
        if target.exists():
            raise LocaleError(
                f"{target.relative_to(config.root)} already exists. "
                f"Run `nvaddon locale-update` to refresh it instead.",
            )
        if language == config.l10n.baseLanguage:
            raise LocaleError(
                f"{language!r} is the add-on's base language, so it is never translated. "
                f"Change [l10n] baseLanguage if that is wrong.",
            )

        catalog = buildCatalog(config)
        catalog.locale = locale
        catalog.fuzzy = False
        created.append(_writeCatalog(target, catalog))

    if created:
        writePot(config)
    return created


def updateLocales(config: AddonConfig, languages: list[str] | None = None) -> dict[str, tuple[int, int]]:
    template = buildCatalog(config)
    targets = languages if languages is not None else discoverLocales(config)
    summary: dict[str, tuple[int, int]] = {}

    for language in targets:
        source = poPath(config, language)
        if not source.is_file():
            raise LocaleError(
                f"No catalogue for {language!r} at {source.relative_to(config.root)}. "
                f"Run `nvaddon locale-add {language}` first.",
            )
        catalog = _readCatalog(config, language)
        catalog.update(template)
        _writeCatalog(source, catalog)

        untranslated = sum(1 for message in catalog if message.id and not message.string)
        fuzzy = sum(1 for message in catalog if message.id and message.fuzzy)
        summary[language] = (untranslated, fuzzy)

    writePot(config)
    return summary


def loadTranslations(config: AddonConfig, language: str) -> dict[str, str]:
    catalog = _readCatalog(config, language)
    translations: dict[str, str] = {}
    for message in catalog:
        if not message.id or message.fuzzy:
            continue
        if isinstance(message.id, str) and isinstance(message.string, str) and message.string:
            translations[message.id] = message.string
    return translations


def compileLocales(config: AddonConfig, languages: list[str] | None = None) -> list[Path]:
    targets = languages if languages is not None else discoverLocales(config)
    compiled: list[Path] = []

    for language in targets:
        catalog = _readCatalog(config, language)
        target = moPath(config, language)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as moFile:
            write_mo(moFile, catalog, use_fuzzy=False)
        compiled.append(target)

    return compiled
