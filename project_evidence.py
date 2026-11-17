"""Inspect an uploaded project ZIP as data and return bounded evidence."""

from io import BytesIO
import json
from pathlib import PurePosixPath
import re
import tomllib
from zipfile import BadZipFile, ZipFile


MAX_PROJECT = 10 * 1024 * 1024
MAX_ENTRY = 256 * 1024
IGNORED = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "vendor"}
LOG_MARKERS = {
    "HTTP 503": re.compile(r"\b503\b|service unavailable", re.I),
    "Connection timeout": re.compile(r"timed?\s*out|timeout", re.I),
    "Connection refused": re.compile(r"econnrefused|connection refused", re.I),
    "Database error": re.compile(r"\b(?:operationalerror|sqlstate|database connection failed)\b", re.I),
    "Login failure": re.compile(r"login failed|authentication failed", re.I),
}


def dependencies(filename, content):
    if filename == "package.json":
        manifest = json.loads(content)
        names = manifest.get("dependencies", {}) if isinstance(manifest, dict) else {}
        return sorted(names) if isinstance(names, dict) else []
    if filename == "pyproject.toml":
        names = tomllib.loads(content).get("project", {}).get("dependencies", [])
        content = "\n".join(item for item in names if isinstance(item, str))
    return re.findall(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?=\s|[<>=!~;\[@]|$)", content, re.M)


def inspect_project(payload, filename):
    if payload is None:
        return {"filename": None, "files": 0, "manifests": [], "signals": [], "skipped": 0}

    report = {"filename": filename, "files": 0, "manifests": [], "signals": [], "skipped": 0}
    try:
        with ZipFile(BytesIO(payload)) as archive:
            members = archive.infolist()
            if len(members) > 2000:
                raise ValueError("The project ZIP can contain up to 2,000 entries.")
            remaining = 2 * 1024 * 1024
            for member in members:
                path = PurePosixPath(member.filename.replace("\\", "/"))
                if member.is_dir() or any(part.lower() in IGNORED for part in path.parts):
                    continue
                if not path.parts or path.is_absolute() or ".." in path.parts or ":" in path.parts[0]:
                    continue
                report["files"] += 1
                basename = path.name.lower()
                is_log = path.suffix.lower() == ".log"
                is_manifest = basename in {"requirements.txt", "pyproject.toml", "package.json"}
                if not (is_log or is_manifest):
                    continue
                if member.file_size > min(MAX_ENTRY, remaining) or member.flag_bits & 1:
                    report["skipped"] += 1
                    continue
                with archive.open(member) as entry:
                    raw = entry.read(member.file_size + 1)
                remaining -= len(raw)
                content = raw.decode("utf-8-sig", errors="replace")
                if is_manifest:
                    try:
                        names = dependencies(basename, content)
                    except (ValueError, TypeError, AttributeError, RecursionError):
                        report["skipped"] += 1
                        continue
                    if len(report["manifests"]) < 10:
                        report["manifests"].append({
                            "path": str(path), "dependencies": sorted(set(names))[:15],
                        })
                if is_log and len(report["signals"]) < 12:
                    for number, line in enumerate(content.splitlines(), 1):
                        markers = [name for name, pattern in LOG_MARKERS.items() if pattern.search(line)]
                        if markers:
                            report["signals"].append({"path": str(path), "line": number, "markers": markers})
                        if len(report["signals"]) >= 12:
                            break
    except (BadZipFile, RuntimeError, NotImplementedError, OSError) as exc:
        raise ValueError("The project ZIP could not be read.") from exc
    return report
