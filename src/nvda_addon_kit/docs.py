# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

import shutil
from pathlib import Path

import markdown

from .models import AddonConfig, AddonMetadata

_IKIWIKI_TITLE: tuple[tuple[str, str], ...] = (
    ('[[!meta title="', "# "),
    ('"]]', " #"),
)


def _renderPage(markdownText: str, title: str, language: str, extensions: list[str]) -> str:
    for directive, replacement in _IKIWIKI_TITLE:
        markdownText = markdownText.replace(directive, replacement, 1)
    body = markdown.markdown(markdownText, extensions=extensions)
    return "\n".join(
        (
            "<!DOCTYPE html>",
            f'<html lang="{language}">',
            "<head>",
            '<meta charset="UTF-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
            '<link rel="stylesheet" type="text/css" href="../style.css" media="screen">',
            f"<title>{title}</title>",
            "</head>\n<body>",
            body,
            "</body>\n</html>",
        ),
    )


def renderDocument(
    source: Path,
    destination: Path,
    *,
    metadata: AddonMetadata,
    translations: dict[str, str],
    extensions: list[str],
) -> Path:
    summary = translations.get(metadata.summary, metadata.summary)
    title = f"{summary} {metadata.version}"
    language = source.parent.name.replace("_", "-")
    html = _renderPage(source.read_text(encoding="utf-8"), title, language, extensions)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding="utf-8")
    return destination


def stageBaseDocuments(config: AddonConfig) -> list[Path]:
    staged: list[Path] = []

    stylesheet = config.root / "style.css"
    if stylesheet.is_file():
        destination = config.docsDir / "style.css"
        destination.parent.mkdir(parents=True, exist_ok=True)
        _ = shutil.copyfile(stylesheet, destination)
        staged.append(destination)

    readme = config.root / "readme.md"
    if readme.is_file():
        destination = config.docsDir / config.l10n.baseLanguage / "readme.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        _ = shutil.copyfile(readme, destination)
        staged.append(destination)

    return staged


def renderAll(
    config: AddonConfig,
    translationsByLanguage: dict[str, dict[str, str]],
    metadata: AddonMetadata | None = None,
) -> list[Path]:
    addon = metadata if metadata is not None else config.addon
    rendered: list[Path] = []

    if not config.docsDir.is_dir():
        return rendered

    for source in sorted(config.docsDir.glob("*/*.md")):
        language = source.parent.name
        translations = translationsByLanguage.get(language, {})
        rendered.append(
            renderDocument(
                source,
                source.with_suffix(".html"),
                metadata=addon,
                translations=translations,
                extensions=config.docs.markdownExtensions,
            ),
        )

    return rendered
