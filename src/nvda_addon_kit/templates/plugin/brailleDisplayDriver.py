# Copyright (C) 2026 %%AUTHOR%%
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

import addonHandler
import braille
import brailleInput
import inputCore

addonHandler.initTranslation()


class BrailleDisplayDriver(braille.BrailleDisplayDriver):
    # Translators: The name of this braille display, shown in NVDA's braille settings.
    description = _("%%SUMMARY%%")
    isThreadSafe = True
    supportsAutomaticDetection = True

    @classmethod
    def check(cls) -> bool:
        return True

    def __init__(self, port="auto"):
        super().__init__()
        self.numCells = 0

    def terminate(self):
        super().terminate()

    def display(self, cells: list[int]):
        raise NotImplementedError

    gestureMap = inputCore.GlobalGestureMap(
        {
            "globalCommands.GlobalCommands": {
                "braille_scrollBack": ("br(%%NAME%%):leftArrow",),
                "braille_scrollForward": ("br(%%NAME%%):rightArrow",),
            },
        },
    )


class InputGesture(braille.BrailleDisplayGesture, brailleInput.BrailleInputGesture):
    source = "%%NAME%%"

    def __init__(self, keyName: str):
        super().__init__()
        self.id = keyName
