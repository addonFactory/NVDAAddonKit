# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

from pathlib import Path

from babel.messages.catalog import Catalog
from babel.messages.extract import DEFAULT_KEYWORDS, extract_from_file

from ..config import CONFIG_FILENAME
from ..models import AddonConfig

DEFAULT_COMMENT_TAGS: tuple[str, ...] = ("Translators:",)


def _iterSourceFiles(config: AddonConfig) -> list[Path]:
    patterns = [*config.build.pythonSources, *config.l10n.extraSources]
    found: set[Path] = set()
    for pattern in patterns:
        for path in config.root.glob(pattern.lstrip("/")):
            if path.is_file():
                found.add(path)
    return sorted(found)


def _relativeLocation(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def buildCatalog(config: AddonConfig, commentTags: tuple[str, ...] = DEFAULT_COMMENT_TAGS) -> Catalog:
    catalog = Catalog(
        project=config.addon.name,
        version=config.addon.version,
        msgid_bugs_address=config.l10n.msgidBugsAddress,
        copyright_holder=config.addon.author,
        charset="utf-8",
    )

    for translatable in config.translatables:
        catalog.add(
            translatable.message,
            locations=[(CONFIG_FILENAME, translatable.lineno)],
            auto_comments=translatable.comment.splitlines() if translatable.comment else [],
        )

    for path in _iterSourceFiles(config):
        location = _relativeLocation(path, config.root)
        extracted = extract_from_file(
            "python",
            path,
            keywords=DEFAULT_KEYWORDS,
            comment_tags=commentTags,
        )
        for lineno, message, comments, context in extracted:
            catalog.add(
                message,
                locations=[(location, lineno)],
                auto_comments=comments,
                context=context,
            )

    return catalog
