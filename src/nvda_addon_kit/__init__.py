# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("nvda-addon-kit")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
