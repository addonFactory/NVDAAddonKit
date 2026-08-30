# Copyright (C) 2026 %%AUTHOR%%
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

import addonHandler
import config
import gui
import ui
import wx
from globalPluginHandler import GlobalPlugin
from gui.settingsDialogs import NVDASettingsDialog, SettingsPanel
from scriptHandler import script

addonHandler.initTranslation()

CONFIG_SECTION = "%%NAME%%"

config.conf.spec[CONFIG_SECTION] = {
    "announceOnStartup": "boolean(default=False)",
}


class AddonSettingsPanel(SettingsPanel):
    # Translators: The title of this add-on's settings category in NVDA's Settings dialog.
    title = _("%%SUMMARY%%")

    def makeSettings(self, settingsSizer):
        helper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
        self.announceCheckBox = helper.addItem(
            wx.CheckBox(
                self,
                # Translators: The label of a checkbox in this add-on's settings.
                label=_("&Announce a greeting when NVDA starts"),
            ),
        )
        self.announceCheckBox.SetValue(config.conf[CONFIG_SECTION]["announceOnStartup"])

    def onSave(self):
        config.conf[CONFIG_SECTION]["announceOnStartup"] = self.announceCheckBox.GetValue()


class GlobalPlugin(GlobalPlugin):
    def __init__(self):
        super().__init__()
        NVDASettingsDialog.categoryClasses.append(AddonSettingsPanel)
        if config.conf[CONFIG_SECTION]["announceOnStartup"]:
            # Translators: Reported when NVDA starts, if the add-on is set to greet the user.
            ui.message(_("%%SUMMARY%% is ready"))

    def terminate(self):
        try:
            NVDASettingsDialog.categoryClasses.remove(AddonSettingsPanel)
        except ValueError:
            pass
        super().terminate()

    @script(
        # Translators: The description of a command, shown in NVDA's Input Gestures dialog.
        description=_("Reports a greeting from %%SUMMARY%%"),
        # Translators: The name of this add-on's category in NVDA's Input Gestures dialog.
        category=_("%%SUMMARY%%"),
        gesture="kb:NVDA+shift+h",
    )
    def script_announceGreeting(self, gesture):
        # Translators: The message reported when the user presses the add-on's command.
        ui.message(_("Hello from %%SUMMARY%%"))
