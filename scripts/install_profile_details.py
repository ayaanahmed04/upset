#!/usr/bin/env python3
"""Install a reviewed profile snapshot and bounded HTML changes with rollback."""

import argparse
import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def target(root, relative):
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError("Target must stay within the project: " + relative)
    for parent in path.parents:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError("Symlink target parent: " + relative)
    if path.exists() and not path.is_file():
        raise ValueError("Expected a regular file: " + relative)
    return path


def atomic_write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".profile-install-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def restore(root, backup, protect=True):
    state = json.loads((backup / "changes.json").read_text())
    if Path(state["project_root"]).resolve() != root:
        raise ValueError("Backup belongs to a different project.")
    for row in state["changes"]:
        path = target(root, row["path"])
        if protect and (not path.exists() or digest(path.read_bytes()) != row["installed_sha256"]):
            raise ValueError("File changed since install; refusing rollback: " + row["path"])
        if row["existed"] and digest((backup / "files" / row["path"]).read_bytes()) != row["previous_sha256"]:
            raise ValueError("Backup checksum differs.")
    for row in reversed(state["changes"]):
        path = target(root, row["path"])
        if row["existed"]:
            atomic_write(path, (backup / "files" / row["path"]).read_bytes())
        else:
            path.unlink(missing_ok=True)
    print("Previous files restored. Restart with data/processed/research_newcomers_v1/upset.sqlite.")


def patch_html(html, changes):
    for old, new in changes:
        if html.count(new) == 1 and old not in html:
            continue
        if html.count(old) != 1 or new in html:
            raise ValueError("HTML differs from the supported display change. No project files changed.")
        html = html.replace(old, new, 1)
    return html


def install(root, package):
    database = target(root, "data/processed/research_newcomers_v1/upset.sqlite")
    if not database.is_file():
        raise ValueError("Install the fighter portraits v2 package first.")
    html_path = target(root, "src/upset/web/research.html")
    html = patch_html(html_path.read_text(), json.loads((package / "ui_changes.json").read_text()))
    module_path = package / "scripts/apply_reviewed_profiles.py"
    spec = importlib.util.spec_from_file_location("reviewed_profiles", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    baseline_hash = digest(database.read_bytes())
    with tempfile.TemporaryDirectory(prefix="upset-profile-details-") as tmp:
        snapshot = Path(tmp) / "snapshot"
        manifest = module.apply_profiles(database, package / "data/mappings/fighter_profile_overrides.json", snapshot)
        planned = {
            "src/upset/web/research.html": html.encode(),
            "src/upset/data/apply_reviewed_profiles.py": module_path.read_bytes(),
            "data/mappings/fighter_profile_overrides.json": (package / "data/mappings/fighter_profile_overrides.json").read_bytes(),
            "scripts/install_profile_details.py": Path(__file__).read_bytes(),
        }
        for file in snapshot.iterdir():
            relative = "data/processed/research_profiles_v1/" + file.name
            existing = target(root, relative)
            raw = file.read_bytes()
            if existing.exists() and existing.read_bytes() != raw:
                raise ValueError("Existing profile snapshot differs; refusing overwrite.")
            planned[relative] = raw
        changes = [(relative, raw) for relative, raw in planned.items()
                   if not target(root, relative).exists() or target(root, relative).read_bytes() != raw]
        if not changes:
            print("Already installed; no files changed.")
            return None
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        backup = root / "data/processed/site_backups" / ("profile-details-" + stamp)
        if not backup.resolve().is_relative_to(root):
            raise ValueError("Backup location must remain within project.")
        backup.mkdir(parents=True)
        state = {"project_root": str(root), "changes": []}
        for relative, raw in changes:
            path = target(root, relative)
            old = path.read_bytes() if path.exists() else None
            if old is not None:
                saved = backup / "files" / relative
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, saved)
            state["changes"].append({"path": relative, "existed": old is not None,
                                     "previous_sha256": digest(old) if old is not None else None,
                                     "installed_sha256": digest(raw)})
        (backup / "changes.json").write_text(json.dumps(state, indent=2) + "\n")
        shutil.copy2(Path(__file__), backup / "restore.py")
        try:
            for relative, raw in changes:
                atomic_write(target(root, relative), raw)
            for row in state["changes"]:
                if digest(target(root, row["path"]).read_bytes()) != row["installed_sha256"]:
                    raise OSError("Installed checksum differs.")
            if digest(database.read_bytes()) != baseline_hash:
                raise OSError("Baseline changed during installation.")
        except Exception:
            restore(root, backup, protect=False)
            raise
    print("Installed: two reviewed profiles; all", manifest["total_bouts"], "fight rows preserved.")
    print("Backup:", backup)
    print("Rollback:", "python3", shlex.quote(str(backup / "restore.py")),
          "--project-root", shlex.quote(str(root)), "--restore", shlex.quote(str(backup)))
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.home() / "Projects/upset")
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--restore", type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve()
    if args.restore:
        restore(root, args.restore.resolve())
    else:
        install(root, args.package.resolve())


if __name__ == "__main__":
    main()
