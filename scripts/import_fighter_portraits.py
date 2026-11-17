#!/usr/bin/env python3
"""Install portraits using explicit UPSET IDs; never join on display names."""

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import struct
import sys
import tempfile
import uuid
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
IMAGE_NAME = re.compile(r"[a-z0-9][a-z0-9_-]*\.png\Z")
PIXEL_STYLE = '<style id="upset-pixel-portraits">.avatar img{image-rendering:pixelated}</style>'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def png_size(raw):
    """Check PNG framing, all CRCs and complete compressed image data."""
    if not raw.startswith(PNG_SIGNATURE) or len(raw) > 20 * 1024 * 1024:
        raise ValueError("Expected a PNG under 20 MiB.")
    offset, size, chunks = 8, None, []
    while offset < len(raw):
        if offset + 12 > len(raw):
            raise ValueError("Truncated PNG.")
        length = struct.unpack(">I", raw[offset:offset + 4])[0]
        kind = raw[offset + 4:offset + 8]
        end = offset + 8 + length
        if end + 4 > len(raw):
            raise ValueError("Truncated PNG chunk.")
        body = raw[offset + 8:end]
        crc = struct.unpack(">I", raw[end:end + 4])[0]
        if zlib.crc32(kind + body) & 0xFFFFFFFF != crc:
            raise ValueError("PNG checksum mismatch.")
        if size is None:
            if kind != b"IHDR" or length != 13:
                raise ValueError("Missing PNG header.")
            size = struct.unpack(">II", body[:8])
            if not all(0 < n <= 4096 for n in size):
                raise ValueError("PNG dimensions must be within 4096 pixels.")
        elif kind == b"IHDR":
            raise ValueError("Duplicate PNG header.")
        if kind == b"IDAT":
            chunks.append(body)
        offset = end + 4
        if kind == b"IEND":
            if length or offset != len(raw) or not chunks:
                raise ValueError("Invalid PNG ending.")
            decoder = zlib.decompressobj()
            decoded = decoder.decompress(b"".join(chunks), 128 * 1024 * 1024)
            if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                raise ValueError("Invalid or excessively large PNG image data.")
            del decoded
            return size
    raise ValueError("Missing PNG ending.")


def images_from(source):
    found = {}

    def add(name, raw):
        if not IMAGE_NAME.fullmatch(name) or name in found:
            raise ValueError(f"Unsafe or duplicate portrait filename: {name}")
        png_size(raw)
        found[name] = raw

    if source.is_dir():
        for path in sorted(source.iterdir()):
            if path.name.startswith(".") or path.suffix.lower() != ".png":
                continue
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"Expected a regular image file: {path.name}")
            add(path.name, path.read_bytes())
    else:
        with zipfile.ZipFile(source) as archive:
            for item in archive.infolist():
                parts = Path(item.filename).parts
                if item.is_dir() or any(p.startswith(".") or p == "__MACOSX" for p in parts):
                    continue
                if Path(item.filename).suffix.lower() != ".png":
                    continue
                if item.file_size > 20 * 1024 * 1024:
                    raise ValueError("Portrait exceeds 20 MiB.")
                add(Path(item.filename).name, archive.read(item))
    if not found:
        raise ValueError("No PNG portraits found.")
    return found


def checked_target(root, relative):
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Target must be relative to the project.")
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError(f"Unsafe target: {relative}")
    for parent in path.parents:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError(f"Symlink target: {relative}")
    return path


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        output.write(data)
    try:
        if path.exists():
            shutil.copymode(path, temporary)
        else:
            temporary.chmod(0o644)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def restore(root, backup, protect=True):
    state = json.loads((backup / "changes.json").read_text())
    if state["project_root"] != str(root):
        raise ValueError("Backup belongs to a different project.")
    for row in state["changes"]:
        path = checked_target(root, row["path"])
        if protect and (not path.exists() or digest(path.read_bytes()) != row["installed_sha256"]):
            raise ValueError(f"File changed since installation; preserve it before rollback: {row['path']}")
        if row["existed"] and digest((backup / "files" / row["path"]).read_bytes()) != row["previous_sha256"]:
            raise ValueError("Backup checksum mismatch.")
    for row in reversed(state["changes"]):
        path = checked_target(root, row["path"])
        if row["existed"]:
            atomic_write(path, (backup / "files" / row["path"]).read_bytes())
        else:
            path.unlink(missing_ok=True)
    print("Restored files from", backup)


def newcomer_update(root, folder, registry, baseline):
    """Prepare a verified additive database and two explicit identities."""
    if baseline is None:
        raise ValueError("The newcomer update requires the existing serving database.")
    metadata = json.loads((folder / "identity_update.json").read_text())
    if metadata.get("schema_version") != 1:
        raise ValueError("Unsupported newcomer update.")
    snapshot = folder / "research_newcomers_v1/upset.sqlite"
    manifest = json.loads((snapshot.parent / "manifest.json").read_text())
    if digest(snapshot.read_bytes()) != manifest["database_sha256"]:
        raise ValueError("New database checksum differs.")
    with sqlite3.connect(baseline.resolve().as_uri() + "?mode=ro", uri=True) as old, sqlite3.connect(snapshot.resolve().as_uri() + "?mode=ro", uri=True) as new:
        if new.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or new.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("New database integrity check failed.")
        baseline_counts = []
        for table in ["fighters", "fights", "stats"]:
            old_rows = set(old.execute("SELECT * FROM " + table).fetchall())
            new_rows = set(new.execute("SELECT * FROM " + table).fetchall())
            if not old_rows <= new_rows:
                raise ValueError("Update would lose or alter existing " + table + ".")
            baseline_counts.append(len(old_rows))
        if tuple(baseline_counts) not in {
            (4455, 8799, 17598),  # retained research_v2
            (4455, 8810, 17620),  # retained research_refresh_v1
            (4456, 8815, 17630),  # retained research_rahiki_v1
            (4458, 8818, 17636),  # this update, for repeat installation
        }:
            raise ValueError("Existing database is not a reviewed supported snapshot.")
        for row in metadata["identities"]:
            saved = new.execute("SELECT profile FROM fighters WHERE id=?", (row["identity"]["upset_fighter_id"],)).fetchone()
            if saved is None or json.loads(saved[0])["source_fighter_id"] != row["provider_link"]["provider_fighter_id"]:
                raise ValueError("New profile and reviewed provider ID differ.")
    for row in metadata["identities"]:
        identity, link = row["identity"], row["provider_link"]
        uid = identity["upset_fighter_id"]
        if link["upset_fighter_id"] != uid or link["provider"] != "cito":
            raise ValueError("Invalid newcomer identity link.")
        matches = [x for x in registry["identities"] if x["upset_fighter_id"] == uid or x["display_name"] == identity["display_name"]]
        if matches and matches != [identity]:
            raise ValueError("New identity conflicts with the project registry.")
        if not matches:
            registry["identities"].append(identity)
        existing = [x for x in registry["provider_links"] if (x["provider"], x["provider_fighter_id"]) == (link["provider"], link["provider_fighter_id"])]
        if existing and any(x["upset_fighter_id"] != uid for x in existing):
            raise ValueError("Reviewed provider ID already belongs to another fighter.")
        if not existing:
            registry["provider_links"].append(link)
    planned = {"data/mappings/fighter_registry.json": json_bytes(registry)}
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        relative = str(path.relative_to(folder))
        if relative.startswith(("research_newcomers_v1/", "cito_current_newcomers_v1/")):
            target = "data/processed/" + relative
            dest = checked_target(root, target)
            raw = path.read_bytes()
            if dest.exists() and dest.read_bytes() != raw:
                raise ValueError("Existing immutable output differs; preserve it for review: " + target)
            planned[target] = raw
        elif relative.startswith("source/"):
            planned[relative.removeprefix("source/")] = path.read_bytes()
    planned["data/roster/newcomer_identity_update.json"] = json_bytes(metadata)
    print("Newcomer database verified: all existing records preserved; updated snapshot includes both reviewed fighters and all three bouts.")
    return snapshot, planned


def install(root, source, manifest_path, database=None, dry_run=False, update=None, registry_path=None,
            roster_file="data/roster/roster.json"):
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("images"), dict):
        raise ValueError("Unsupported portrait manifest.")
    if update and registry_path:
        raise ValueError("Newcomer updates use the project registry. Import portraits separately with --registry.")
    registry = json.loads((registry_path or root / "data/mappings/fighter_registry.json").read_text())
    supplemental = {}
    if update:
        database, supplemental = newcomer_update(root, update, registry, database)
    ids = {x["upset_fighter_id"] for x in registry["identities"]}
    links = {(x["upset_fighter_id"], x["provider"], x["provider_fighter_id"]) for x in registry["provider_links"]}
    incoming = images_from(source)
    roster_path = checked_target(root, roster_file)
    if roster_path.parent != root / "data/roster" or not roster_path.stem.startswith("roster") or roster_path.suffix != ".json":
        raise ValueError("Roster must be a roster*.json file in data/roster.")
    suffix = roster_path.stem.removeprefix("roster")
    roster = json.loads(roster_path.read_text()) if roster_path.exists() else {
        "as_of": manifest["reviewed_on"],
        "source": "UPSET portrait collection; images only, contract status unverified",
        "fighters": {},
    }
    if not isinstance(roster.get("fighters"), dict):
        raise ValueError("Existing roster must contain a fighters dictionary.")
    datetime.strptime(roster["as_of"], "%Y-%m-%d")
    # Validate every ID/provider anchor before touching any project file.
    used, linked, pending = set(), [], []
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) if database else None
    try:
        for name in sorted(incoming):
            row = manifest["images"].get(name)
            if row is None:
                pending.append({"image": name, "reason": manifest.get("pending", {}).get(name, {}).get("reason", "No reviewed filename-to-ID mapping; retained unlinked.")})
                continue
            fid, anchor = row["upset_fighter_id"], row["identity_anchor"]
            uuid.UUID(fid)
            provider = anchor.get("provider", "ufcstats")
            if fid not in ids or (fid, provider, anchor["source_fighter_id"]) not in links or fid in used:
                raise ValueError(f"Invalid or conflicting permanent identity anchor: {name}")
            used.add(fid)
            if connection:
                record = connection.execute("SELECT profile FROM fighters WHERE id=?", (fid,)).fetchone()
                if record is None or json.loads(record[0]).get("source_fighter_id") != anchor["source_fighter_id"]:
                    raise ValueError(f"Serving database identity disagrees with manifest: {name}")
            previous = roster["fighters"].get(anchor["source_fighter_id"], {})
            if not isinstance(previous, dict):
                raise ValueError(f"Invalid existing provider-keyed roster entry: {name}")
            entry = roster["fighters"].setdefault(fid, dict(previous))
            if not isinstance(entry, dict):
                raise ValueError(f"Invalid existing roster entry: {fid}")
            entry.update(image=name, image_credit="Illustration: UPSET", image_kind="illustration")
            linked.append({"image": name, "upset_fighter_id": fid, "sha256": digest(incoming[name])})
    finally:
        if connection:
            connection.close()
    html_path = checked_target(root, "src/upset/web/research.html")
    html = html_path.read_text()
    if "function avatar(" not in html or ".avatar img" not in html or "</head>" not in html:
        raise ValueError("Expected the existing fighter-avatar site. No source changes made.")
    if "image-rendering:pixelated" not in html.replace(" ", "") and PIXEL_STYLE not in html:
        html = html.replace("</head>", PIXEL_STYLE + "\n</head>", 1)
    report = {"schema_version": 1, "linked_count": len(linked), "pending_count": len(pending), "linked": linked, "pending": pending}
    planned = {f"data/roster/media/{name}": raw for name, raw in incoming.items()}
    planned.update({
        str(roster_path.relative_to(root)): json_bytes(roster),
        f"data/roster/portrait_manifest{suffix}.json": json_bytes(manifest),
        f"data/roster/portrait_import_report{suffix}.json": json_bytes(report),
        "src/upset/web/research.html": html.encode(),
        "scripts/import_fighter_portraits.py": Path(__file__).read_bytes(),
    })
    planned.update(supplemental)
    changes = []
    for relative, raw in planned.items():
        path = checked_target(root, relative)
        if path.exists() and not path.is_file():
            raise ValueError(f"Expected a regular target file: {relative}")
        if not path.exists() or path.read_bytes() != raw:
            changes.append((relative, raw))
    print(f"Portraits: {len(linked)} linked; {len(pending)} retained unlinked; {len(changes)} files to change.")
    for row in pending:
        print("Pending:", row["image"], "—", row["reason"])
    if dry_run or not changes:
        return report, None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup = checked_target(root, f"data/processed/site_backups/portraits-{stamp}")
    backup.mkdir(parents=True)
    state = {"project_root": str(root), "changes": []}
    for relative, raw in changes:
        path = checked_target(root, relative)
        existed = path.exists()
        old = path.read_bytes() if existed else None
        if existed:
            saved = backup / "files" / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, saved)
        state["changes"].append({"path": relative, "existed": existed, "previous_sha256": digest(old) if old is not None else None, "installed_sha256": digest(raw)})
    (backup / "changes.json").write_bytes(json_bytes(state))
    # Include the self-contained importer so rollback survives moving the package.
    shutil.copy2(Path(__file__), backup / "restore.py")
    try:
        for relative, raw in changes:
            atomic_write(checked_target(root, relative), raw)
        for row in state["changes"]:
            if digest(checked_target(root, row["path"]).read_bytes()) != row["installed_sha256"]:
                raise OSError("Installed file checksum mismatch.")
    except Exception:
        restore(root, backup, protect=False)
        raise
    print("Backup:", backup)
    print("Rollback command:")
    import shlex
    print("python3", shlex.quote(str(backup / "restore.py")), "--project-root", shlex.quote(str(root)), "--restore", shlex.quote(str(backup)))
    return report, backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--archive", type=Path, help="Updated portrait ZIP or directory of PNGs")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--roster", default="data/roster/roster.json", help="Roster path relative to the project.")
    parser.add_argument("--database", type=Path, help="Optional read-only serving ID check")
    parser.add_argument("--registry", type=Path, help="Reviewed identity registry for the selected serving database")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--newcomer-update", type=Path, help="Verified additive identity/database bundle")
    parser.add_argument("--restore", type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve()
    if args.restore:
        restore(root, args.restore.resolve())
        return
    suffix = Path(args.roster).stem.removeprefix("roster")
    manifest = args.manifest or root / f"data/roster/portrait_manifest{suffix}.json"
    if not args.archive:
        parser.error("--archive is required for an import")
    install(root, args.archive, manifest, args.database, args.dry_run, args.newcomer_update, args.registry,
            args.roster)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Portrait import stopped:", error, file=sys.stderr)
        sys.exit(1)
