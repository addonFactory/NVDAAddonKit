# Copyright (C) 2026 %%AUTHOR%%
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

import addonHandler
from speech.commands import IndexCommand
from synthDriverHandler import SynthDriver, synthIndexReached

addonHandler.initTranslation()


class SynthDriver(SynthDriver):
    # Translators: The name of this speech synthesiser, shown in NVDA's synthesiser list.
    description = _("%%SUMMARY%%")

    supportedSettings = (
        SynthDriver.VoiceSetting(),
        SynthDriver.RateSetting(),
        SynthDriver.PitchSetting(),
        SynthDriver.VolumeSetting(),
    )
    supportedCommands = {IndexCommand}
    supportedNotifications = {synthIndexReached}

    @classmethod
    def check(cls) -> bool:
        return True

    def __init__(self):
        super().__init__()

    def terminate(self):
        super().terminate()

    def speak(self, speechSequence):
        raise NotImplementedError

    def cancel(self):
        raise NotImplementedError

    def pause(self, switch: bool):
        raise NotImplementedError

    def _get_rate(self) -> int:
        raise NotImplementedError

    def _set_rate(self, rate: int):
        raise NotImplementedError

    def _get_pitch(self) -> int:
        raise NotImplementedError

    def _set_pitch(self, pitch: int):
        raise NotImplementedError

    def _get_volume(self) -> int:
        raise NotImplementedError

    def _set_volume(self, volume: int):
        raise NotImplementedError
