#!/usr/bin/env python3
"""
Save the photos and videos from a Telegram Desktop chat export into one folder per sender.

Export the chat first: in Telegram Desktop, open the chat, then menu (⋮) ->
Export chat history -> tick "Photos" and "Videos" (and "Files" for images sent
uncompressed), format "Machine-readable JSON". You get a folder that holds
result.json.

Copy this script into that folder, open a terminal there and run:

    python3 save_media_by_sender.py

The sorted files land in output/ inside the current folder.
--input points at an export somewhere else; --output chooses where the sorted
files go.

Needs Python 3.8+ and no third-party packages. See README.md in the
repository for details, including what is skipped and why.
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".tif", ".tiff", ".bmp"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".3gp"}
# media_type values worth keeping. Missing media_type = a document sent "as file".
VIDEO_MEDIA_TYPES = {"video_file", "video_message"}  # regular and round videos
SKIPPED_MEDIA_TYPES = {"sticker", "animation", "voice_message", "audio_file"}  # animation = GIF


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_name(name: str, fallback: str = "Unknown sender") -> str:
    """Make untrusted text (sender or group name) usable as a single path component.

    Drops control and invisible formatting characters (incl. bidi overrides that
    can disguise a name), replaces separators and characters macOS/Windows reject,
    strips leading/trailing dots so "." and ".." can't occur, and caps the length
    at 100 UTF-8 bytes (macOS allows 255 per component; prefix mode needs room).
    """
    name = unicodedata.normalize("NFC", str(name or ""))
    name = "".join(c for c in name if unicodedata.category(c) not in {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    encoded = name.encode("utf-8")[:100]
    name = encoded.decode("utf-8", errors="ignore").strip(" .")
    return name or fallback


def unique_labels(entities: dict) -> dict:
    """Map key -> label; keys whose labels collide get " (<key>)" appended.

    entities: {key: label}. Used for senders (key = from_id) and for chats
    (key = chat id) so that neither two people nor two groups end up merged.
    """
    # Compared case-insensitively: macOS and Windows file systems would merge
    # "Anna" and "anna" into one folder.
    by_label = defaultdict(list)
    for key, label in entities.items():
        by_label[label.casefold()].append(key)
    result = {}
    for keys in by_label.values():
        for key in keys:
            label = entities[key]
            result[key] = f"{label} ({safe_name(key, 'unknown')})" if len(keys) > 1 else label
    return result


def fit_name(name: str, limit: int = 255) -> str:
    """Shorten a file name's stem so the whole name fits in `limit` UTF-8 bytes."""
    path = Path(name)
    stem, suffix = path.stem, path.suffix
    budget = limit - len(suffix.encode("utf-8"))
    return stem.encode("utf-8")[:budget].decode("utf-8", errors="ignore") + suffix


def sender_key(msg: dict) -> str:
    return str(msg.get("from_id") or msg.get("from") or "")


def is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def message_media(msg: dict):
    """Yield (relative path, "photo" | "video") for media attached to a message.

    Only "photo" and "file" are used. The "thumbnail" key (Telegram's own
    small preview, saved as <file>_thumb.jpg) is deliberately ignored. Stickers
    (static ones are image/webp) and GIFs (stored as mp4 "animation") are pack
    artwork or GIF-search results, not the sender's own, so they're skipped too.
    """
    media_type = msg.get("media_type")
    if media_type in SKIPPED_MEDIA_TYPES:
        return
    photo = msg.get("photo")
    if isinstance(photo, str) and photo:
        yield photo, "photo"
    file = msg.get("file")
    if isinstance(file, str) and file and not file.lower().endswith("_thumb.jpg"):
        mime = (msg.get("mime_type") or "").lower()
        suffix = Path(file).suffix.lower()
        if media_type in VIDEO_MEDIA_TYPES or mime.startswith("video/") or suffix in VIDEO_EXT:
            yield file, "video"
        elif mime.startswith("image/") or suffix in IMAGE_EXT:
            yield file, "photo"


HTML_EXPORT_FILES = ("messages.html", "export_results.html")  # an HTML export has these instead of result.json


def html_export_hint(folder: Path, marker: str) -> str:
    return (f"{folder} holds an HTML export ({marker}), which this script can't read.\n"
            "In Telegram Desktop, export the chat again and set the format to 'Machine-readable JSON'. "
            "The new folder will hold result.json.")


def locate_export(given, prog: str):
    """Find the folder that holds result.json.

    Returns (folder, None), or (None, message) telling the user what to do.
    Without --input, the script's own folder is tried first, so it can be
    dropped into an export and run with no arguments, then the current folder.
    """
    if given:
        folder = Path(given).expanduser()
        if (folder / "result.json").is_file():
            return folder, None
        if not folder.is_dir():
            return None, f"Folder not found: {folder}"
        for marker in HTML_EXPORT_FILES:
            if (folder / marker).is_file():
                return None, html_export_hint(folder, marker)
        return None, (f"No result.json in {folder}.\n"
                      "Point --input at the folder Telegram Desktop created when exporting the chat: "
                      "it holds result.json next to a photos/ folder.")
    candidates = list(dict.fromkeys([Path(__file__).resolve().parent, Path.cwd()]))
    for folder in candidates:
        if (folder / "result.json").is_file():
            return folder, None
    for folder in candidates:
        for marker in HTML_EXPORT_FILES:
            if (folder / marker).is_file():
                return None, html_export_hint(folder, marker)
    return None, ("result.json not found next to this script or in the current folder.\n"
                  "Copy the script into the export folder (the one that holds result.json) and run it "
                  f"from there, or say where the export is:  python3 {prog} --input <export folder>")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-i", "--input", metavar="FOLDER",
                    help="the export folder, the one that holds result.json "
                         "(default: the folder this script is in, or else the current folder)")
    ap.add_argument("-o", "--output", metavar="FOLDER",
                    help="where the sorted photos and videos go (default: ./output)")
    ap.add_argument("--mode", choices=["folders", "prefix"], default="folders",
                    help="folders: one subfolder per sender (default); "
                         "prefix: one flat folder with files named '<Sender>__<original name>'")
    ap.add_argument("--move", action="store_true",
                    help="move files instead of copying (modifies the export folder)")
    ap.add_argument("--keep-duplicates", action="store_true",
                    help="also copy byte-identical images that appear more than once "
                         "(forwards, re-posts); Telegram's *_thumb.jpg previews are never copied")
    args = ap.parse_args()

    export, problem = locate_export(args.input, ap.prog)
    if problem:
        print(problem, file=sys.stderr)
        return 1
    result = export / "result.json"
    print(f"Reading {result.resolve()}")

    with result.open(encoding="utf-8") as f:
        data = json.load(f)

    # Single-chat export: {"name": ..., "messages": [...]}
    # Full-account export: {"chats": {"list": [{"name": ..., "messages": [...]}, ...]}}
    if "messages" in data:
        chats = [data]
    else:
        chats = data.get("chats", {}).get("list", [])

    # A single chat goes straight into the output folder: <out>/<Sender>/.
    # A full-account export gets one folder per chat: <out>/<Chat>/<Sender>/.
    out_root = Path(args.output).expanduser() if args.output else Path("output")
    if len(chats) == 1:
        chat_dirs = [out_root]
    else:
        chat_labels = unique_labels({
            str(i): safe_name(chat.get("name"), f"Chat {chat.get('id', i)}") for i, chat in enumerate(chats)
        })
        chat_dirs = [out_root / chat_labels[str(i)] for i in range(len(chats))]

    # Sender labels are computed per output folder, from each sender's latest name.
    names_by_dir = defaultdict(dict)  # out dir -> {sender key: safe display name}
    for chat, out in zip(chats, chat_dirs):
        for msg in chat.get("messages", []):
            if msg.get("type") == "message":
                names_by_dir[out][sender_key(msg)] = safe_name(msg.get("from") or msg.get("from_id"))
    labels_by_dir = {out: unique_labels(names) for out, names in names_by_dir.items()}

    counts = Counter()
    kinds = Counter()
    missing = skipped_placeholders = skipped_duplicates = unsafe = 0
    seen_hashes = {}  # sha256 -> first destination path

    for chat, out in zip(chats, chat_dirs):
        out.mkdir(parents=True, exist_ok=True)
        for msg in chat.get("messages", []):
            if msg.get("type") != "message":
                continue
            sender = labels_by_dir[out][sender_key(msg)]
            for rel, kind in message_media(msg):
                src = export / rel
                if not is_inside(src, export):
                    # result.json is untrusted: never copy files from outside the export.
                    unsafe += 1
                    continue
                if not src.is_file():
                    # Telegram writes "(File not included. Change data exporting settings...)"
                    # when a size limit or unticked category excluded the file.
                    if rel.startswith("("):
                        skipped_placeholders += 1
                    else:
                        missing += 1
                    continue
                if not args.keep_duplicates:
                    digest = file_hash(src)
                    if digest in seen_hashes:
                        skipped_duplicates += 1
                        continue
                if args.mode == "folders":
                    dest_dir = out / sender
                    dest = dest_dir / src.name
                else:
                    dest_dir = out
                    dest = out / fit_name(f"{sender}__{src.name}", 240)
                dest_dir.mkdir(parents=True, exist_ok=True)
                # Avoid silently overwriting if two files share a name. is_symlink()
                # also catches dangling links, which copy2 would write through.
                n = 1
                while dest.exists() or dest.is_symlink():
                    dest = dest.with_name(f"{dest.stem}_{n}{dest.suffix}")
                    n += 1
                (shutil.move if args.move else shutil.copy2)(str(src), str(dest))
                if not args.keep_duplicates:
                    seen_hashes[digest] = dest
                counts[(out, sender)] += 1
                kinds[kind] += 1

    per_chat = len(chat_dirs) > 1
    print(f"{'Moved' if args.move else 'Copied'} {kinds['photo']} photo(s) and {kinds['video']} video(s).")
    for (out, sender), n in counts.most_common():
        print(f"  {n:5d}  {sender}" + (f"  [{out.name}]" if per_chat else ""))
    if skipped_duplicates:
        print(f"  {skipped_duplicates} byte-identical repeat(s) skipped (use --keep-duplicates to copy them).")
    if skipped_placeholders:
        print(f"  {skipped_placeholders} photo(s)/video(s) were not included in the export "
              f"(size limit, or 'Photos'/'Videos' unticked) — re-export with a higher limit.")
    if missing:
        print(f"  {missing} file(s) listed in result.json are missing from the export folder "
              f"(the export is incomplete, or files were moved out of it). Export again if they matter.")
    if unsafe:
        print(f"  {unsafe} path(s) in result.json pointed outside the export folder and were ignored.")
    if kinds["photo"] + kinds["video"]:
        print(f"\nYour photos and videos are in {out_root.resolve()}. Go and see them!")
    else:
        print("\nNothing was copied. If the chat does have photos, check that 'Photos' and 'Videos' "
              "were ticked when exporting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
