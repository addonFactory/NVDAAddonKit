# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

from .catalogs import (
    addLocales,
    compileLocales,
    discoverLocales,
    loadTranslations,
    moPath,
    poPath,
    updateLocales,
    writePot,
)
from .extract import buildCatalog

__all__ = [
    "addLocales",
    "buildCatalog",
    "compileLocales",
    "discoverLocales",
    "loadTranslations",
    "moPath",
    "poPath",
    "updateLocales",
    "writePot",
]
