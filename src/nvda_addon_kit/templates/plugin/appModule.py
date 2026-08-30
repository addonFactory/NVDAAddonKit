# Copyright (C) 2026 %%AUTHOR%%
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

import addonHandler
import appModuleHandler
import ui
from scriptHandler import script

addonHandler.initTranslation()


class AppModule(appModuleHandler.AppModule):
    def event_NVDAObject_init(self, obj):
        super().event_NVDAObject_init(obj)

    @script(
        # Translators: The description of a command, shown in NVDA's Input Gestures dialog.
        description=_("Reports the status bar of the current application"),
        # Translators: The name of this add-on's category in NVDA's Input Gestures dialog.
        category=_("%%SUMMARY%%"),
        gesture="kb:NVDA+shift+s",
    )
    def script_reportStatus(self, gesture):
        statusBar = self.getStatusBar()
        if statusBar is None:
            # Translators: Reported when the application has no status bar to read.
            ui.message(_("No status bar found"))
            return
        ui.message(self.getStatusBarText(statusBar))
