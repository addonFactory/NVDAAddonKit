# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__, build as buildModule, config as configModule, l10n
from .errors import AddonKitError
from .models import AddonConfig, Channel

PLUGIN_KINDS: tuple[str, ...] = (
    "globalPlugin",
    "appModule",
    "synthDriver",
    "brailleDisplayDriver",
    "visionEnhancementProvider",
    "none",
)


def _loadConfig(args: argparse.Namespace) -> AddonConfig:
    start = Path(args.directory) if getattr(args, "directory", None) else None
    return configModule.load(start)


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def cmdInit(args: argparse.Namespace) -> int:
    from .scaffold import initialiseAddon

    destination = Path(args.directory_positional or args.directory or ".").resolve()
    created = initialiseAddon(destination, args)
    print(f"Created {len(created)} files in {destination}")
    print("\nNext steps:")
    print(f"  cd {destination.name}")
    print("  nvaddon build")
    return 0


def cmdBuild(args: argparse.Namespace) -> int:
    config = _loadConfig(args)
    result = buildModule.build(
        config,
        version=args.version,
        channel=args.channel,
        output=Path(args.output) if args.output else None,
    )
    if result.languages:
        print(f"Compiled {len(result.languages)} translations: {', '.join(result.languages)}")
    if result.documents:
        print(f"Rendered {len(result.documents)} documentation pages")
    print(f"Built {_relative(result.bundle, config.root)} ({result.bundle.stat().st_size:,} bytes)")
    return 0


def cmdInstall(args: argparse.Namespace) -> int:
    from .install import handOffToNVDA, linkAddon

    config = _loadConfig(args)
    nvdaPath = Path(args.nvda_path) if args.nvda_path else None

    if args.link:
        metadata = buildModule.resolveMetadata(config, version=args.version, channel=args.channel)
        _ = buildModule.prepare(config, metadata)
        link = linkAddon(config, nvdaPath)
        print(f"Linked {_relative(config.addonDir, config.root)} to {link}")
        print("Restart NVDA, or reload plugins, to pick up the add-on.")
        return 0

    result = buildModule.build(config, version=args.version, channel=args.channel)
    handOffToNVDA(result.bundle)
    print(f"Opened {result.bundle.name} with NVDA. Confirm the installation prompt to finish.")
    return 0


def cmdPot(args: argparse.Namespace) -> int:
    config = _loadConfig(args)
    destination = Path(args.output) if args.output else None
    potFile = l10n.writePot(config, merge=args.merge, destination=destination)
    catalog = l10n.buildCatalog(config)
    count = sum(1 for message in catalog if message.id)
    print(f"Wrote {_relative(potFile, config.root)} with {count} messages")
    return 0


def cmdLocaleAdd(args: argparse.Namespace) -> int:
    config = _loadConfig(args)
    created = l10n.addLocales(config, args.languages)
    for path in created:
        print(f"Created {_relative(path, config.root)}")
    return 0


def cmdLocaleUpdate(args: argparse.Namespace) -> int:
    config = _loadConfig(args)
    summary = l10n.updateLocales(config, args.languages or None)
    if not summary:
        print("No translations to update.")
        return 0
    for language, (untranslated, fuzzy) in summary.items():
        details = [f"{untranslated} untranslated"]
        if fuzzy:
            details.append(f"{fuzzy} fuzzy")
        print(f"{language}: {', '.join(details)}")
    return 0


def cmdLocaleCompile(args: argparse.Namespace) -> int:
    config = _loadConfig(args)
    compiled = l10n.compileLocales(config, args.languages or None)
    if not compiled:
        print("No translations to compile.")
        return 0
    for path in compiled:
        print(f"Compiled {_relative(path, config.root)}")
    return 0


def cmdCheck(args: argparse.Namespace) -> int:
    config = _loadConfig(args)
    issues = configModule.validate(config)
    errors = [issue for issue in issues if issue.level == "error"]
    warnings = [issue for issue in issues if issue.level == "warning"]

    for issue in errors + warnings:
        print(issue, file=sys.stderr if issue.level == "error" else sys.stdout)

    if not issues:
        print(f"{config.addon.name} {config.addon.version}: no problems found.")
        return 0

    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s).")
    return 1 if errors else 0


def cmdClean(args: argparse.Namespace) -> int:
    config = _loadConfig(args)
    removed = buildModule.clean(config)
    if not removed:
        print("Nothing to clean.")
        return 0
    for path in removed:
        print(f"Removed {_relative(path, config.root)}")
    print(f"\nRemoved {len(removed)} build outputs.")
    return 0


def cmdMigrate(args: argparse.Namespace) -> int:
    from .migrate import migrateBuildVars

    start = Path(args.directory) if args.directory else Path.cwd()
    source = Path(args.buildvars) if args.buildvars else start / "buildVars.py"
    destination = Path(args.output) if args.output else start / configModule.CONFIG_FILENAME

    result = migrateBuildVars(source, destination, force=args.force)
    print(f"Wrote {destination} from {source}")
    for note in result.notes:
        print(f"  note: {note}")
    print("\nReview the result, then run `nvaddon check` and `nvaddon build`.")
    print("Once the build output looks right, delete buildVars.py, sconstruct and site_scons/.")
    return 0


def cmdRelease(args: argparse.Namespace) -> int:
    from .release import release

    config = _loadConfig(args)
    configPath = configModule.findConfig(config.root)

    plan = release(
        configPath,
        args.version,
        args.channel,
        push=not args.no_push,
        changelog=args.changelog,
    )

    print(f"{config.addon.version} -> {plan.version} on the {plan.channel} channel")
    print(f"Committed and tagged {plan.tag}")
    if plan.pushed:
        print("Pushed the commit and the tag together.")
    else:
        print("Not pushed. When you are ready:")
        print(f"  git push --atomic origin HEAD refs/tags/{plan.tag}")
    return 0


def cmdCrowdin(args: argparse.Namespace) -> int:
    from .crowdin import runCrowdin

    config = _loadConfig(args)
    return runCrowdin(config, args)


def _addInitArguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "directory_positional",
        nargs="?",
        metavar="directory",
        help="where to create the add-on (default: current directory)",
    )
    parser.add_argument("--name", help="add-on name, internal to NVDA (e.g. myAddon)")
    parser.add_argument("--summary", help="user visible name of the add-on")
    parser.add_argument("--description", help="longer description shown in the add-on store")
    parser.add_argument("--author", help='author, as "Name <email@example.com>"')
    parser.add_argument("--addon-version", default=None, help="initial version (default: 1.0.0)")
    parser.add_argument("--url", help="URL of the add-on's documentation or homepage")
    parser.add_argument("--source-url", help="URL of the source repository")
    parser.add_argument("--license", help='licence name (e.g. "GPL v2")')
    parser.add_argument("--license-url", help="URL of the licence text")
    parser.add_argument("--min-nvda", help="minimum supported NVDA version (e.g. 2024.1)")
    parser.add_argument("--last-tested", help="most recent NVDA version tested (e.g. 2025.3)")
    parser.add_argument("--base-language", help="language the add-on is written in (default: en)")
    parser.add_argument("--plugin", choices=PLUGIN_KINDS, help="starter plugin to scaffold")
    parser.add_argument(
        "--no-ci",
        action="store_true",
        help="skip GitHub workflows, issue templates and the Crowdin sync",
    )
    parser.add_argument(
        "--no-tooling",
        action="store_true",
        help="skip the lint configuration and the Python version pin",
    )
    parser.add_argument(
        "-y", "--yes", action="store_true", help="do not prompt; take every answer from flags and defaults"
    )
    parser.add_argument("--force", action="store_true", help="write into a non-empty directory")


def _addVersionArguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--version", metavar="VERSION", help="override the version for this build")
    parser.add_argument(
        "--channel",
        type=Channel,
        choices=list(Channel),
        help="override the update channel for this build",
    )


def _addLanguageArgument(parser: argparse.ArgumentParser, *, required: bool, action: str) -> None:
    parser.add_argument(
        "languages",
        nargs="+" if required else "*",
        metavar="LANG",
        help="language codes, e.g. de pt_BR" if required else f"languages to {action} (default: all)",
    )


def buildParser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nvaddon",
        description="Scaffold, build, translate and install NVDA add-ons.",
    )
    parser.add_argument("--version", action="version", version=f"nvda-addon-kit {__version__}")
    parser.add_argument(
        "-C",
        "--directory",
        metavar="PATH",
        help="run as though started in PATH",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    init = subparsers.add_parser("init", help="create a new add-on")
    _addInitArguments(init)
    init.set_defaults(func=cmdInit)

    build = subparsers.add_parser("build", help="build the .nvda-addon")
    _addVersionArguments(build)
    build.add_argument(
        "-o", "--output", metavar="PATH", help="write the add-on here instead of the default name"
    )
    build.set_defaults(func=cmdBuild)

    install = subparsers.add_parser("install", help="build and install into NVDA")
    install.add_argument(
        "--link",
        action="store_true",
        help="link the working tree into NVDA's add-ons directory instead of installing a built add-on",
    )
    install.add_argument("--nvda-path", metavar="PATH", help="target a portable NVDA copy at PATH")
    _addVersionArguments(install)
    install.set_defaults(func=cmdInstall)

    pot = subparsers.add_parser("pot", help="generate the translation template")
    pot.add_argument(
        "--merge",
        action="store_true",
        help="omit the header and source locations, for merging into catalogues",
    )
    pot.add_argument("-o", "--output", metavar="PATH", help="write the template here")
    pot.set_defaults(func=cmdPot)

    localeAdd = subparsers.add_parser("locale-add", help="start a new translation")
    _addLanguageArgument(localeAdd, required=True, action="add")
    localeAdd.set_defaults(func=cmdLocaleAdd)

    localeUpdate = subparsers.add_parser(
        "locale-update", help="merge new messages into existing translations"
    )
    _addLanguageArgument(localeUpdate, required=False, action="update")
    localeUpdate.set_defaults(func=cmdLocaleUpdate)

    localeCompile = subparsers.add_parser("locale-compile", help="compile translations to .mo files")
    _addLanguageArgument(localeCompile, required=False, action="compile")
    localeCompile.set_defaults(func=cmdLocaleCompile)

    check = subparsers.add_parser("check", help="validate addon.toml without building")
    check.set_defaults(func=cmdCheck)

    clean = subparsers.add_parser("clean", help="remove generated build outputs")
    clean.set_defaults(func=cmdClean)

    migrate = subparsers.add_parser("migrate", help="convert buildVars.py to addon.toml")
    migrate.add_argument("--buildvars", metavar="PATH", help="path to buildVars.py")
    migrate.add_argument("-o", "--output", metavar="PATH", help="path to write addon.toml to")
    migrate.add_argument("--force", action="store_true", help="overwrite an existing addon.toml")
    migrate.set_defaults(func=cmdMigrate)

    release = subparsers.add_parser("release", help="set the version and channel, tag, and push the release")
    release.add_argument("version", help="major, minor, patch, or an explicit version such as 1.2.3")
    release.add_argument(
        "--channel",
        type=Channel,
        choices=list(Channel),
        default=Channel.STABLE,
        help="channel to release on (default: stable); the tag is <version>-<channel>",
    )
    release.add_argument("--no-push", action="store_true", help="commit and tag locally without pushing")
    release.add_argument("--changelog", action="store_true", help="add a stub entry to changelog.md")
    release.set_defaults(func=cmdRelease)

    crowdin = subparsers.add_parser("crowdin", help="sync translations with Crowdin")
    crowdin.add_argument("action", choices=("upload", "download", "status"), help="what to sync")
    crowdin.add_argument("--project-id", type=int, help="Crowdin project id (default: $CROWDIN_PROJECT_ID)")
    crowdin.add_argument("--token", help="Crowdin API token (default: $CROWDIN_TOKEN)")
    crowdin.add_argument(
        "--min-percent",
        type=int,
        default=50,
        help="minimum translated percentage to download a language (default: 50)",
    )
    crowdin.set_defaults(func=cmdCrowdin)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = buildParser()
    args = parser.parse_args(argv)

    if not getattr(args, "func", None):
        parser.print_help()
        return 2

    try:
        return args.func(args)
    except AddonKitError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
