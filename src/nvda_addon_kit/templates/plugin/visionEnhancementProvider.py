# Copyright (C) 2026 %%AUTHOR%%
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

import addonHandler
import vision

addonHandler.initTranslation()


class VisionEnhancementProviderSettings(vision.providerBase.VisionEnhancementProviderSettings):
    @classmethod
    def getId(cls) -> str:
        return "%%NAME%%"

    @classmethod
    def getDisplayName(cls) -> str:
        # Translators: The name of this vision enhancement provider, shown in NVDA's vision settings.
        return _("%%SUMMARY%%")

    @classmethod
    def _get_supportedSettings(cls):
        return []


class VisionEnhancementProvider(vision.providerBase.VisionEnhancementProvider):
    _settings = VisionEnhancementProviderSettings()

    @classmethod
    def getSettings(cls) -> VisionEnhancementProviderSettings:
        return cls._settings

    @classmethod
    def getSettingsPanelClass(cls):
        return None

    @classmethod
    def canStart(cls) -> bool:
        return True

    def registerEventExtensionPoints(self, extensionPoints):
        pass

    def terminate(self):
        super().terminate()
