# nvda-addon-kit

Scaffold, build, translate and install [NVDA](https://www.nvaccess.org/) add-ons from a single
`addon.toml`.

This is the successor to the SCons-based `addonTemplate`. Instead of forking a template repository and editing `buildVars.py`, you install a tool:

```console
pip install nvda-addon-kit
nvaddon init myAddon
cd myAddon
nvaddon build
```

## Commands

| Command | Does |
| --- | --- |
| `nvaddon init [dir]` | Create a new add-on, interactively or from flags |
| `nvaddon build` | Produce `<name>-<version>.nvda-addon` |
| `nvaddon install` | Build, then hand the add-on to NVDA to install |
| `nvaddon install --link` | Link the working tree into NVDA's add-ons directory for development |
| `nvaddon pot` | Generate `<name>.pot` from Python sources and `addon.toml` |
| `nvaddon locale-add <lang>…` | Start a new translation |
| `nvaddon locale-update` | Merge new messages into every existing translation |
| `nvaddon locale-compile` | Compile `.po` files and translated manifests |
| `nvaddon check` | Validate `addon.toml` against add-on store rules |
| `nvaddon clean` | Remove generated build outputs |
| `nvaddon migrate` | Modernise a SCons-era add-on: config, build machinery, CI, pyproject |
| `nvaddon release <version>` | Set version and channel, commit, tag `<version>-<channel>`, and push |
| `nvaddon crowdin` | Sync translations with Crowdin |

Run `nvaddon <command> --help` for the flags each one accepts.

## Releasing

```console
nvaddon release 1.2.0 --channel beta
```

This writes the version and channel into `addon.toml`, commits, tags
`1.2.0-beta`, and pushes the commit and tag with `git push --atomic` so the
remote takes both or neither. If anything fails the working tree is restored to
where it started, leaving no half-made release behind. Use `--no-push` to stop
before publishing.

Tags doesn't have prefix by default. If your addon's published tags already have it, You can configure it like below:

```toml
[release]
tagPrefix = "v"      # produces v1.2.0-beta instead of 1.2.0-beta
```

`--tag-prefix` overrides it for a single release.

## addon.toml

```toml
[addon]
name = "myAddon"
# Translators: Summary/title for this add-on, shown on install and in the add-on store.
summary = "Add-on user visible name"
# Translators: Long description shown for this add-on in the add-on store.
description = """Description for the add-on.
It can span multiple lines."""
version = "1.0.0"
author = "Name <name@domain.com>"
minimumNVDAVersion = "2024.1"
lastTestedNVDAVersion = "2025.3"

[build]
pythonSources = ["addon/globalPlugins/**/*.py"]

[l10n]
baseLanguage = "en"
```

The comment above a translatable key becomes that string's translator note in the generated
`.pot`, exactly as `# Translators:` comments in `buildVars.py` did:

```pot
#. Translators: Summary/title for this add-on, shown on install and in the add-on store.
#: addon.toml:3
msgid "Add-on user visible name"
msgstr ""
```

## Migrating an existing add-on

```console
cd myExistingAddon
pip install nvda-addon-kit
nvaddon migrate
nvaddon check
nvaddon build
```

`migrate --apply` removes `buildVars.py`, `sconstruct` and `site_scons/` for you. It refuses to
run on a dirty working tree, so `git diff` shows exactly what changed.

## Licence

GNU General Public License version 2 or later. See [COPYING.txt](COPYING.txt).
