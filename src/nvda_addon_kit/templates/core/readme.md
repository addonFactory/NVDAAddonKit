# %%SUMMARY%%

%%DESCRIPTION%%

* Author: %%AUTHOR%%
* NVDA compatibility: %%MIN_NVDA%% to %%LAST_TESTED%%
* Download: %%URL%%

This file is your add-on's user documentation. `nvaddon build` renders it to
`readme.html` inside the add-on, which is what NVDA opens when a user chooses
Help in the Add-on Store. Write it for the people using the add-on, not for
people working on it.

## Commands

| Command | Description |
| --- | --- |
| NVDA+shift+h | Reports a greeting from %%SUMMARY%%. |

Assign different keys from NVDA's Input Gestures dialog, under the
"%%SUMMARY%%" category.

## Settings

Open NVDA's Settings dialog and choose the "%%SUMMARY%%" category to change how
the add-on behaves.

## Translating this add-on

Translators are welcome. To start a new language:

```console
nvaddon locale-add <language code>
```

Then translate `addon/locale/<language code>/LC_MESSAGES/nvda.po` and open a
pull request.

## Licence

%%LICENSE%%. See COPYING.txt for the full text.
