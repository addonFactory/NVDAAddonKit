# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

from copy import replace
from dataclasses import dataclass
from pathlib import Path

from . import docs, l10n
from .bundle import createBundle
from .manifest import writeManifest, writeTranslatedManifest
from .models import AddonConfig, AddonMetadata, Channel


@dataclass(frozen=True)
class PreparedAddon:
    metadata: AddonMetadata
    languages: list[str]
    documents: list[Path]

    def defaultBundlePath(self, root: Path) -> Path:
        return root / f"{self.metadata.name}-{self.metadata.version}.nvda-addon"


@dataclass(frozen=True)
class BuildResult:
    bundle: Path
    metadata: AddonMetadata
    languages: list[str]
    documents: list[Path]


def resolveMetadata(
    config: AddonConfig,
    *,
    version: str | None = None,
    channel: Channel | None = None,
) -> AddonMetadata:
    metadata = config.addon
    if channel is not None:
        metadata = replace(metadata, updateChannel=channel)
    if version:
        metadata = replace(metadata, version=version)
    return metadata


def prepare(config: AddonConfig, metadata: AddonMetadata) -> PreparedAddon:
    writeManifest(config, metadata)

    languages = l10n.discoverLocales(config)
    translationsByLanguage: dict[str, dict[str, str]] = {}
    for language in languages:
        translations = l10n.loadTranslations(config, language)
        translationsByLanguage[language] = translations
        writeTranslatedManifest(config, language, translations, metadata)
    l10n.compileLocales(config, languages)

    docs.stageBaseDocuments(config)
    documents = docs.renderAll(config, translationsByLanguage, metadata)

    return PreparedAddon(metadata=metadata, languages=languages, documents=documents)


def build(
    config: AddonConfig,
    *,
    version: str | None = None,
    channel: Channel | None = None,
    output: Path | None = None,
) -> BuildResult:
    metadata = resolveMetadata(config, version=version, channel=channel)
    prepared = prepare(config, metadata)

    destination = output or prepared.defaultBundlePath(config.root)
    bundle = createBundle(config.addonDir, destination, config.build.excludedFiles)

    return BuildResult(
        bundle=bundle,
        metadata=prepared.metadata,
        languages=prepared.languages,
        documents=prepared.documents,
    )


def _removeFile(path: Path, removed: list[Path]) -> None:
    if path.is_file():
        path.unlink()
        removed.append(path)


def clean(config: AddonConfig) -> list[Path]:
    removed: list[Path] = []

    _removeFile(config.addonDir / "manifest.ini", removed)
    _removeFile(config.docsDir / "style.css", removed)

    for language in l10n.discoverLocales(config):
        _removeFile(l10n.moPath(config, language), removed)
        _removeFile(config.localeDir / language / "manifest.ini", removed)

    if config.docsDir.is_dir():
        for html in sorted(config.docsDir.glob("*/*.html")):
            _removeFile(html, removed)
        baseDocs = config.docsDir / config.l10n.baseLanguage
        if baseDocs.is_dir():
            for staged in sorted(baseDocs.glob("*.md")):
                _removeFile(staged, removed)
            if not any(baseDocs.iterdir()):
                baseDocs.rmdir()
                removed.append(baseDocs)

    for bundle in sorted(config.root.glob("*.nvda-addon")):
        _removeFile(bundle, removed)
    for potFile in sorted(config.root.glob("*.pot")):
        _removeFile(potFile, removed)

    return removed
