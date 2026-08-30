# Copyright (C) 2026 NVDA add-on kit contributors
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

import argparse
import os
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from .errors import AddonKitError
from .l10n import poPath, writePot
from .models import AddonConfig

type Record = dict[str, Any]

LANGUAGE_MAPPINGS: dict[str, str] = {
    "af_ZA": "af",
    "de_CH": "de-CH",
    "es": "es-ES",
    "es_CO": "es-CO",
    "nb_NO": "nb",
    "ne": "ne-NP",
    "nn_NO": "nn-NO",
    "pt_PT": "pt-PT",
    "pt_BR": "pt-BR",
    "sr": "sr-CS",
    "zh_CN": "zh-CN",
    "zh_HK": "zh-HK",
    "zh_TW": "zh-TW",
}

_CROWDIN_TO_NVDA: dict[str, str] = {crowdin: nvda for nvda, crowdin in LANGUAGE_MAPPINGS.items()}

_PAGE_SIZE = 100
_DOWNLOAD_TIMEOUT = 60


def crowdinLanguage(nvdaLanguage: str) -> str:
    return LANGUAGE_MAPPINGS.get(nvdaLanguage, nvdaLanguage.replace("_", "-"))


def nvdaLanguage(crowdinId: str) -> str:
    if crowdinId in _CROWDIN_TO_NVDA:
        return _CROWDIN_TO_NVDA[crowdinId]
    match crowdinId.split("-"):
        case [language, region]:
            return f"{language}_{region}"
        case _:
            return crowdinId


def _client(args: argparse.Namespace) -> Any:
    try:
        from crowdin_api import CrowdinClient
    except ImportError as exc:
        raise AddonKitError(
            "The Crowdin API client is not installed. Install it with:\n"
            "  pip install 'nvda-addon-kit[crowdin]'",
        ) from exc

    token = args.token or os.environ.get("CROWDIN_TOKEN") or os.environ.get("crowdinAuthToken")  # noqa: SIM112 - name set by NV Access's workflow
    if not token:
        raise AddonKitError(
            "No Crowdin API token. Pass --token, or set the CROWDIN_TOKEN environment variable.",
        )

    return CrowdinClient(token=token)


def _projectId(args: argparse.Namespace) -> int:
    raw = args.project_id or os.environ.get("CROWDIN_PROJECT_ID")
    if not raw:
        raise AddonKitError(
            "No Crowdin project id. Pass --project-id, or set the CROWDIN_PROJECT_ID environment variable.",
        )
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise AddonKitError(f"{raw!r} is not a valid Crowdin project id.") from exc


def _paginate(endpoint: Callable[..., Any], **parameters: Any) -> Iterator[Record]:
    offset = 0
    while True:
        response = endpoint(limit=_PAGE_SIZE, offset=offset, **parameters)
        entries = response["data"]
        for entry in entries:
            yield entry["data"]
        if len(entries) < _PAGE_SIZE:
            return
        offset += _PAGE_SIZE


def _findSourceFileId(client: Any, projectId: int, fileName: str) -> int | None:
    target = fileName.lower()
    for entry in _paginate(client.source_files.list_files, projectId=projectId):
        if entry["path"].lower().endswith(target):
            return int(entry["id"])
    return None


def _sourceFileId(client: Any, projectId: int, fileName: str) -> int:
    fileId = _findSourceFileId(client, projectId, fileName)
    if fileId is None:
        raise AddonKitError(f"{fileName} has not been uploaded to Crowdin project {projectId} yet.")
    return fileId


def _progressByLanguage(client: Any, projectId: int, fileId: int) -> dict[str, int]:
    return {
        entry["languageId"]: int(entry["translationProgress"])
        for entry in _paginate(
            client.translation_status.get_file_progress,
            projectId=projectId,
            fileId=fileId,
        )
    }


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT) as response:
        destination.write_bytes(response.read())


def _commandStatus(
    config: AddonConfig,
    client: Any,
    projectId: int,
    args: argparse.Namespace,
) -> int:
    fileId = _sourceFileId(client, projectId, config.potPath.name)
    progress = _progressByLanguage(client, projectId, fileId)

    for languageId, percent in sorted(progress.items(), key=lambda item: (-item[1], item[0])):
        marker = "" if percent >= args.min_percent else "  (below threshold)"
        print(f"{nvdaLanguage(languageId):<10} {percent:>3}%{marker}")
    print(f"\n{len(progress)} languages, threshold {args.min_percent}%.")
    return 0


def _commandUpload(config: AddonConfig, client: Any, projectId: int) -> int:
    potFile = writePot(config)
    print(f"Regenerated {potFile.name}")

    with potFile.open("rb") as handle:
        storage = client.storages.add_storage(handle)
    storageId = storage["data"]["id"]

    fileId = _findSourceFileId(client, projectId, potFile.name)
    if fileId is None:
        client.source_files.add_file(projectId=projectId, storageId=storageId, name=potFile.name)
        print(f"Uploaded {potFile.name} to Crowdin project {projectId} as a new source file.")
    else:
        client.source_files.update_or_restore_file(
            projectId=projectId,
            fileId=fileId,
            storageId=storageId,
        )
        print(f"Updated {potFile.name} in Crowdin project {projectId}.")
    return 0


def _commandDownload(
    config: AddonConfig,
    client: Any,
    projectId: int,
    args: argparse.Namespace,
) -> int:
    fileId = _sourceFileId(client, projectId, config.potPath.name)
    progress = _progressByLanguage(client, projectId, fileId)

    downloaded = 0
    for languageId, percent in sorted(progress.items()):
        language = nvdaLanguage(languageId)
        if language == config.l10n.baseLanguage:
            continue
        if percent < args.min_percent:
            print(f"Skipped {language}: {percent}% translated, below {args.min_percent}%")
            continue

        exported = client.translations.export_project_translation(
            projectId=projectId,
            targetLanguageId=languageId,
            fileIds=[fileId],
        )
        destination = poPath(config, language)
        _download(exported["data"]["url"], destination)
        print(f"Downloaded {language} ({percent}%) to {destination.relative_to(config.root)}")
        downloaded += 1

    print(f"\nDownloaded {downloaded} translations.")
    print("Run `nvaddon build` to compile them into the add-on.")
    return 0


def runCrowdin(config: AddonConfig, args: argparse.Namespace) -> int:
    client = _client(args)
    projectId = _projectId(args)

    match args.action:
        case "status":
            return _commandStatus(config, client, projectId, args)
        case "upload":
            return _commandUpload(config, client, projectId)
        case _:
            return _commandDownload(config, client, projectId, args)
