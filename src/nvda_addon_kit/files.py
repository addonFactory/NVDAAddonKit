# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

from pathlib import Path


def writeText(path: Path, text: str) -> Path:
    # Two separate sources of CRLF have to be shut off. `newline="\n"` stops
    # Python translating "\n" to os.linesep when writing on Windows, and the
    # replace handles content that already carries CRLF -- tomlkit round-trips
    # whatever line endings the source file had.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
    return path
