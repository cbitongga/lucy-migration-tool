"""Conservative file inventory and heuristic C# discovery, never feature proof."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

TEXT_EXTENSIONS = {".cs", ".csproj", ".sln", ".cshtml", ".razor", ".aspx", ".ascx",
                   ".config", ".xml", ".sql", ".json", ".js", ".jsx", ".ts", ".tsx",
                   ".java", ".properties", ".yml", ".yaml", ".html", ".css", ".resx"}
PATTERNS = [
    ("route", re.compile(r'\[(?:Route|HttpGet|HttpPost|HttpPut|HttpDelete|HttpPatch)\b')),
    ("type", re.compile(r'\b(?:class|interface|record|enum|struct)\s+[A-Za-z_]\w*')),
    ("database", re.compile(r'\b(?:DbSet|DbContext|SqlCommand|ExecuteSql|FromSql|StoredProcedure)\b')),
    ("exception", re.compile(r'\b(?:throw|catch)\b')),
    ("dynamic", re.compile(r'\b(?:Assembly\.Load|Activator\.CreateInstance|GetType\(|dynamic\b)')),
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    with path.open("rb") as handle:
        h = hashlib.sha256()
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
        return h.hexdigest()


def inventory(config: dict, base: Path, candidates: bool = False) -> dict:
    files, hints, gaps, exclusions = [], [], [], []
    excluded = set(config["exclude_dirs"])
    for root in config["roots"]:
        directory = (base / root["path"]).resolve()
        if not directory.is_dir():
            gaps.append({"root": root["id"], "path": "", "reason": "root_missing"})
            continue
        def walk_error(error):
            gaps.append({"root": root["id"], "path": str(error.filename), "reason": "unreadable_directory"})
        for parent, dirs, names in os.walk(directory, followlinks=False, onerror=walk_error):
            for name in sorted(dirs[:]):
                p = Path(parent) / name
                relative = p.relative_to(directory).as_posix()
                if p.is_symlink():
                    dirs.remove(name)
                    gaps.append({"root": root["id"], "path": relative, "reason": "symlink_directory"})
                elif name in excluded:
                    dirs.remove(name)
                    exclusions.append({"root": root["id"], "path": relative, "reason": "configured_directory_exclusion"})
            dirs.sort()
            for name in sorted(names):
                p = Path(parent) / name
                relative = p.relative_to(directory).as_posix()
                if p.is_symlink():
                    gaps.append({"root": root["id"], "path": relative, "reason": "symlink_file"})
                    continue
                try:
                    before = p.stat()
                    sha = hash_file(p)
                    after = p.stat()
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        gaps.append({"root": root["id"], "path": relative, "reason": "changed_during_scan"})
                    eligible = p.suffix.lower() in TEXT_EXTENSIONS and after.st_size <= config["max_file_bytes"]
                    item = {"root": root["id"], "path": relative, "role": root["role"],
                            "sha256": sha, "bytes": after.st_size, "text_eligible": eligible}
                    files.append(item)
                    if not eligible:
                        if root["role"] == "source":
                            gaps.append({"root": root["id"], "path": relative, "reason": "not_text_analyzed"})
                        continue
                    if candidates and root["role"] == "source":
                        try:
                            data = p.read_bytes()
                            if digest(data) != sha:
                                gaps.append({"root": root["id"], "path": relative, "reason": "changed_during_analysis"})
                                continue
                            text = data.decode("utf-8-sig")
                        except UnicodeError:
                            gaps.append({"root": root["id"], "path": relative, "reason": "non_utf8"})
                            continue
                        # Excerpts are intentionally omitted: inspect selected source through packets.
                        if p.suffix.lower() in {".cshtml", ".razor", ".aspx", ".ascx"}:
                            hints.append({"root": root["id"], "path": relative, "line": 1, "kind": "ui_file", "confidence": "heuristic"})
                        if p.suffix.lower() == ".cs":
                            for line, value in enumerate(text.splitlines(), 1):
                                for kind, regex in PATTERNS:
                                    if regex.search(value):
                                        hints.append({"root": root["id"], "path": relative, "line": line,
                                                      "kind": kind, "confidence": "heuristic"})
                except OSError:
                    gaps.append({"root": root["id"], "path": relative, "reason": "unreadable_file"})
    return {"files": sorted(files, key=lambda x: (x["root"], x["path"])),
            "candidates": hints, "gaps": gaps, "exclusions": exclusions,
            "discovery_level": "file inventory plus heuristic hints; semantic/runtime discovery incomplete"}
