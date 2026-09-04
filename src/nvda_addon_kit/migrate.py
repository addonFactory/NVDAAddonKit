# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

import ast
from dataclasses import dataclass, field
from pathlib import Path

from .errors import AddonKitError
from .files import writeText

_METADATA_KEYS: tuple[tuple[str, str], ...] = (
    ("addon_name", "name"),
    ("addon_summary", "summary"),
    ("addon_description", "description"),
    ("addon_version", "version"),
    ("addon_changelog", "changelog"),
    ("addon_author", "author"),
    ("addon_url", "url"),
    ("addon_sourceURL", "sourceURL"),
    ("addon_docFileName", "docFileName"),
    ("addon_minimumNVDAVersion", "minimumNVDAVersion"),
    ("addon_lastTestedNVDAVersion", "lastTestedNVDAVersion"),
    ("addon_updateChannel", "updateChannel"),
    ("addon_license", "license"),
    ("addon_licenseURL", "licenseURL"),
)

_TRANSLATABLE = frozenset({"summary", "description", "changelog"})

_NESTED_TABLES: tuple[str, ...] = ("brailleTables", "symbolDictionaries", "speechDictionaries")


@dataclass
class MigrationResult:
    destination: Path
    notes: list[str] = field(default_factory=list)


def _literal(node: ast.AST) -> object:
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_"
        and len(node.args) == 1
    ):
        return _literal(node.args[0])

    if isinstance(node, ast.Dict):
        mapping: dict[str, object] = {}
        for keyNode, valueNode in zip(node.keys, node.values, strict=True):
            if keyNode is None:
                continue
            key = _literal(keyNode)
            if isinstance(key, str):
                mapping[key] = _literal(valueNode)
        return mapping

    if isinstance(node, (ast.List, ast.Tuple)):
        return [_literal(element) for element in node.elts]

    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return None


def _commentsAbove(lines: list[str], lineno: int) -> list[str]:
    comments: list[str] = []
    index = lineno - 2
    while index >= 0:
        stripped = lines[index].strip()
        if not stripped.startswith("#"):
            break
        text = stripped.lstrip("#")
        comments.append(text.removeprefix(" "))
        index -= 1
    return list(reversed(comments))


def _findAssignment(tree: ast.Module, name: str) -> ast.AST | None:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
            and node.value
        ):
            return node.value
    return None


def _parseAddonInfo(node: ast.AST, lines: list[str]) -> tuple[dict[str, object], dict[str, list[str]]]:
    values: dict[str, object] = {}
    comments: dict[str, list[str]] = {}

    if isinstance(node, ast.Dict):
        for keyNode, valueNode in zip(node.keys, node.values, strict=True):
            if keyNode is None or not isinstance(keyNode, ast.Constant):
                continue
            key = keyNode.value
            if not isinstance(key, str):
                continue
            values[key] = _literal(valueNode)
            comments[key] = _commentsAbove(lines, keyNode.lineno)
    elif isinstance(node, ast.Call):
        for keyword in node.keywords:
            if keyword.arg is None:
                continue
            values[keyword.arg] = _literal(keyword.value)
            comments[keyword.arg] = _commentsAbove(lines, keyword.value.lineno)
    else:
        raise AddonKitError(
            "buildVars.py: `addon_info` is neither a dict literal nor an AddonInfo(...) call, "
            "so it cannot be read without running the file. Convert it by hand.",
        )

    return values, comments


def _parseSources(tree: ast.Module, name: str) -> list[str]:
    node = _findAssignment(tree, name)
    if node is None:
        return []

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _literal(node.left)
        right = _literal(node.right)
        combined: list[str] = []
        for part in (left, right):
            if isinstance(part, list):
                combined.extend(str(item) for item in part)
        return combined

    value = _literal(node)
    return [str(item) for item in value] if isinstance(value, list) else []


def _tomlString(value: str) -> str:
    if "\n" in value:
        escaped = value.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
        return f'"""{escaped}"""'
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _tomlArray(values: list[str]) -> str:
    if not values:
        return "[]"
    items = ", ".join(_tomlString(value) for value in values)
    return f"[{items}]"


def _nestedComments(node: ast.AST, lines: list[str]) -> dict[tuple[str, str], list[str]]:
    comments: dict[tuple[str, str], list[str]] = {}
    if not isinstance(node, ast.Dict):
        return comments

    for entryKey, entryValue in zip(node.keys, node.values, strict=True):
        if entryKey is None or not isinstance(entryKey, ast.Constant):
            continue
        entryName = entryKey.value
        if not isinstance(entryName, str) or not isinstance(entryValue, ast.Dict):
            continue
        for attributeKey in entryValue.keys:
            if attributeKey is None or not isinstance(attributeKey, ast.Constant):
                continue
            attribute = attributeKey.value
            if isinstance(attribute, str):
                comments[(entryName, attribute)] = _commentsAbove(lines, attributeKey.lineno)

    return comments


def _renderNested(
    name: str,
    entries: dict[str, object],
    comments: dict[tuple[str, str], list[str]],
    output: list[str],
) -> None:
    for entryName, attributes in entries.items():
        if not isinstance(attributes, dict):
            continue
        output.append("")
        output.append(f"[{name}.{_tomlString(str(entryName))}]")
        for key, value in attributes.items():
            for comment in comments.get((entryName, key), []):
                output.append(f"# {comment}")
            if isinstance(value, bool):
                output.append(f"{key} = {'true' if value else 'false'}")
            else:
                output.append(f"{key} = {_tomlString(str(value))}")


def convertBuildVars(source: str) -> tuple[str, list[str]]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise AddonKitError(f"buildVars.py could not be parsed: {exc}") from exc

    lines = source.splitlines()
    notes: list[str] = []

    addonInfoNode = _findAssignment(tree, "addon_info")
    if addonInfoNode is None:
        raise AddonKitError("buildVars.py does not define `addon_info`, so there is nothing to migrate.")
    values, comments = _parseAddonInfo(addonInfoNode, lines)

    output: list[str] = [
        "# Configuration for this NVDA add-on, migrated from buildVars.py.",
        "#",
        "# The comment directly above a translatable string is that string's note to",
        "# translators, and is carried into the generated .pot file.",
        "",
        "[addon]",
    ]

    for sourceKey, targetKey in _METADATA_KEYS:
        if sourceKey not in values:
            continue
        value = values[sourceKey]
        for comment in comments.get(sourceKey, []):
            output.append(f"# {comment}")
        if value is None:
            output.append(f'{targetKey} = ""')
        else:
            output.append(f"{targetKey} = {_tomlString(str(value))}")
        if targetKey in _TRANSLATABLE:
            output.append("")

    version = values.get("addon_version")
    if isinstance(version, str) and version.count(".") != 2:
        notes.append(
            f"version was {version!r}, which the NVDA add-on store rejects. "
            f"Change it to major.minor.patch, e.g. 1.0.0.",
        )

    pythonSources = _parseSources(tree, "pythonSources")
    excludedFiles = _parseSources(tree, "excludedFiles")
    i18nSources = _parseSources(tree, "i18nSources")

    extraSources = [item for item in i18nSources if item not in pythonSources and item != "buildVars.py"]

    output.extend(
        [
            "",
            "[build]",
            "# The Python files that make up this add-on, scanned for translatable strings.",
            f"pythonSources = {_tomlArray(pythonSources)}",
            "",
            "# Files inside the `addon` directory to leave out of the built add-on.",
            f"excludedFiles = {_tomlArray(excludedFiles)}",
        ],
    )

    baseLanguageNode = _findAssignment(tree, "baseLanguage")
    baseLanguage = _literal(baseLanguageNode) if baseLanguageNode is not None else "en"
    output.extend(
        [
            "",
            "[l10n]",
            "# The language this add-on is written in.",
            f"baseLanguage = {_tomlString(str(baseLanguage or 'en'))}",
            "",
            "# Extra files to scan for translatable strings.",
            f"extraSources = {_tomlArray(extraSources)}",
        ],
    )

    markdownNode = _findAssignment(tree, "markdownExtensions")
    markdownValue = _literal(markdownNode) if markdownNode is not None else None
    markdownExtensions = [str(item) for item in markdownValue] if isinstance(markdownValue, list) else []
    output.extend(
        [
            "",
            "[docs]",
            "# Python-Markdown extensions used when rendering documentation.",
            f"markdownExtensions = {_tomlArray(markdownExtensions)}",
        ],
    )

    for tableName in _NESTED_TABLES:
        node = _findAssignment(tree, tableName)
        entries = _literal(node) if node is not None else None
        if isinstance(entries, dict) and entries:
            _renderNested(tableName, entries, _nestedComments(node, lines) if node else {}, output)
            notes.append(f"{tableName} was migrated; check each entry against NVDA's documentation.")

    if extraSources:
        notes.append(
            f"i18nSources listed {', '.join(extraSources)} beyond pythonSources; "
            f"these were kept as [l10n] extraSources.",
        )

    return "\n".join(output) + "\n", notes


def migrateBuildVars(source: Path, destination: Path, *, force: bool = False) -> MigrationResult:
    if not source.is_file():
        raise AddonKitError(
            f"{source} does not exist. Point --buildvars at the buildVars.py to convert.",
        )
    if destination.exists() and not force:
        raise AddonKitError(f"{destination} already exists. Pass --force to overwrite it.")

    text, notes = convertBuildVars(source.read_text(encoding="utf-8"))
    writeText(destination, text)
    return MigrationResult(destination=destination, notes=notes)
