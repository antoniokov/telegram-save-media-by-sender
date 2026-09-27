"""Tests for save_media_by_sender.py against a synthetic Telegram Desktop export.

Run from the repo root:  python3 -m unittest discover -s tests
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "save_media_by_sender.py"
DEFAULT_OUT = "output"


def make_export(root: Path) -> None:
    """Build a small export mirroring Telegram Desktop's result.json layout."""
    (root / "photos").mkdir(parents=True)
    (root / "files").mkdir()
    messages = [
        # Photo sent as a file: Telegram writes the file plus <file>_thumb.jpg
        {"id": 1, "type": "message", "date": "2025-01-02T10:11:12", "from": "Anna Kowalska",
         "from_id": "user111", "file": "files/IMG_4821.jpg", "file_name": "IMG_4821.jpg",
         "thumbnail": "files/IMG_4821.jpg_thumb.jpg", "mime_type": "image/jpeg", "text": ""},
        # Normal compressed photo
        {"id": 2, "type": "message", "date": "2025-01-02T10:12:00", "from": "Piotr / Nowak: Team?",
         "from_id": "user222", "photo": "photos/photo_2@02-01-2025_10-12-00.jpg", "text": ""},
        # Same file forwarded again by someone else (byte-identical)
        {"id": 3, "type": "message", "date": "2025-01-03T09:00:00", "from": "Piotr / Nowak: Team?",
         "from_id": "user222", "file": "files/IMG_4821 (2).jpg", "file_name": "IMG_4821.jpg",
         "thumbnail": "files/IMG_4821 (2).jpg_thumb.jpg", "mime_type": "image/jpeg", "text": ""},
        # Non-image file: must be ignored
        {"id": 4, "type": "message", "date": "2025-01-03T09:01:00", "from": "Anna Kowalska",
         "from_id": "user111", "file": "files/report.pdf", "mime_type": "application/pdf", "text": ""},
        # Service message: must be ignored
        {"id": 5, "type": "service", "date": "2025-01-03T09:02:00", "actor": "Anna Kowalska",
         "action": "pin_message", "text": ""},
        # Sender with no display name: falls back to from_id
        {"id": 6, "type": "message", "date": "2025-01-04T09:02:00", "from": None, "from_id": "user333",
         "photo": "photos/photo_6@04-01-2025_09-02-00.jpg", "text": ""},
        # Excluded by export size limit
        {"id": 7, "type": "message", "date": "2025-01-04T09:03:00", "from": "Anna Kowalska",
         "from_id": "user111",
         "photo": "(File not included. Change data exporting settings to download.)", "text": ""},
        # HEIC sent as a file
        {"id": 8, "type": "message", "date": "2025-01-05T09:00:00", "from": "Anna Kowalska",
         "from_id": "user111", "file": "files/IMG_0001.HEIC", "mime_type": "image/heic", "text": ""},
    ]
    (root / "result.json").write_text(
        json.dumps({"name": "Test group", "type": "private_supergroup", "id": 123, "messages": messages}),
        encoding="utf-8",
    )
    contents = {
        "files/IMG_4821.jpg": b"ORIGINAL-BYTES-AAAA",
        "files/IMG_4821.jpg_thumb.jpg": b"thumb",
        "files/IMG_4821 (2).jpg": b"ORIGINAL-BYTES-AAAA",
        "files/IMG_4821 (2).jpg_thumb.jpg": b"thumb2",
        "files/report.pdf": b"%PDF",
        "files/IMG_0001.HEIC": b"HEIC",
        "photos/photo_2@02-01-2025_10-12-00.jpg": b"PHOTO-2",
        "photos/photo_6@04-01-2025_09-02-00.jpg": b"PHOTO-6",
    }
    for rel, data in contents.items():
        (root / rel).write_bytes(data)


def make_account_export(root: Path, chats: list, files: dict) -> None:
    """Rewrite the single-chat result.json in `root` as a full-account export that also holds `chats`."""
    result = root / "result.json"
    first = json.loads(result.read_text(encoding="utf-8"))
    result.write_text(json.dumps({"chats": {"list": [first, *chats]}}), encoding="utf-8")
    for rel, content in files.items():
        (root / rel).write_bytes(content)


def run(*args: str, cwd=None, script: Path = SCRIPT, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True, check=check, cwd=cwd)


def add_messages(root: Path, messages: list, files: dict, **chat_fields) -> None:
    result = root / "result.json"
    data = json.loads(result.read_text(encoding="utf-8"))
    data["messages"] += messages
    data.update(chat_fields)
    result.write_text(json.dumps(data), encoding="utf-8")
    for rel, content in files.items():
        (root / rel).write_bytes(content)


def listing(root: Path) -> set:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


OTHER_CHAT = {
    "name": "Other group", "type": "private_supergroup", "id": 456, "messages": [
        {"id": 1, "type": "message", "from": "Zofia Lis", "from_id": "user444",
         "photo": "photos/photo_z.jpg", "text": ""},
    ],
}
OTHER_CHAT_FILES = {"photos/photo_z.jpg": b"PHOTO-Z"}


class SaveMediaBySenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.export = Path(self.tmp.name) / "export"
        self.out = Path(self.tmp.name) / "out"
        make_export(self.export)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def sort(self, *extra: str, **kwargs) -> subprocess.CompletedProcess:
        """Run the script on the fixture export with explicit input and output folders."""
        return run("--input", str(self.export), "--output", str(self.out), *extra, **kwargs)

    def script_in(self, folder: Path) -> Path:
        """Copy the script into `folder`, as a user does when dropping it into an export."""
        folder.mkdir(parents=True, exist_ok=True)
        return Path(shutil.copy(SCRIPT, folder / SCRIPT.name))

    def test_folders_mode_skips_thumbs_pdfs_and_exact_duplicates(self) -> None:
        result = self.sort()
        self.assertEqual(listing(self.out), {
            "Anna Kowalska/IMG_4821.jpg",
            "Anna Kowalska/IMG_0001.HEIC",
            "Piotr _ Nowak_ Team_/photo_2@02-01-2025_10-12-00.jpg",
            "user333/photo_6@04-01-2025_09-02-00.jpg",
        })
        self.assertIn("1 byte-identical repeat(s) skipped", result.stdout)
        self.assertIn("1 photo(s)/video(s) were not included in the export", result.stdout)
        self.assertIn(f"Your photos and videos are in {self.out.resolve()}", result.stdout)

    def test_prefix_mode(self) -> None:
        self.sort("--mode", "prefix")
        self.assertIn("Anna Kowalska__IMG_4821.jpg", listing(self.out))
        self.assertIn("user333__photo_6@04-01-2025_09-02-00.jpg", listing(self.out))

    def test_keep_duplicates(self) -> None:
        self.sort("--keep-duplicates")
        self.assertIn("Piotr _ Nowak_ Team_/IMG_4821 (2).jpg", listing(self.out))

    def test_export_folder_untouched_by_default(self) -> None:
        before = listing(self.export)
        self.sort()
        self.assertEqual(before, listing(self.export))

    def test_short_flags(self) -> None:
        run("-i", str(self.export), "-o", str(self.out))
        self.assertIn("Anna Kowalska/IMG_4821.jpg", listing(self.out))

    def test_script_dropped_into_export_runs_with_no_arguments(self) -> None:
        script = self.script_in(self.export)
        result = run(script=script, cwd=self.tmp.name)
        out = Path(self.tmp.name) / DEFAULT_OUT
        self.assertIn("Anna Kowalska/IMG_4821.jpg", listing(out))
        self.assertIn(f"Your photos and videos are in {out.resolve()}", result.stdout)
        # The output goes to the current folder, not into the export.
        self.assertFalse((self.export / DEFAULT_OUT).exists())

    def test_script_elsewhere_reads_the_current_folder(self) -> None:
        script = self.script_in(Path(self.tmp.name) / "elsewhere")
        run(script=script, cwd=str(self.export))
        self.assertIn("Anna Kowalska/IMG_4821.jpg", listing(self.export / DEFAULT_OUT))

    def test_missing_result_json_is_explained(self) -> None:
        script = self.script_in(Path(self.tmp.name) / "elsewhere")
        result = run(script=script, cwd=self.tmp.name, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Copy the script into the export folder", result.stderr)
        self.assertIn("--input", result.stderr)
        result = run("--input", str(Path(self.tmp.name) / "nope"), check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Folder not found", result.stderr)

    def test_html_export_is_explained(self) -> None:
        html = Path(self.tmp.name) / "ChatExport_html"
        html.mkdir()
        (html / "messages.html").write_text("<html></html>", encoding="utf-8")
        result = run("--input", str(html), check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Machine-readable JSON", result.stderr)
        # Same when the script was dropped into the HTML export.
        result = run(script=self.script_in(html), cwd=self.tmp.name, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Machine-readable JSON", result.stderr)

    def test_files_missing_from_export_are_explained(self) -> None:
        add_messages(self.export, [
            {"id": 9, "type": "message", "from": "Anna Kowalska", "from_id": "user111",
             "photo": "photos/gone.jpg", "text": ""},
        ], {})
        result = self.sort()
        self.assertIn("1 file(s) listed in result.json are missing from the export folder", result.stdout)

    def test_empty_chat_says_nothing_was_copied(self) -> None:
        (self.export / "result.json").write_text(
            json.dumps({"name": "Quiet group", "id": 1, "messages": []}), encoding="utf-8")
        result = self.sort()
        self.assertIn("Nothing was copied", result.stdout)
        self.assertNotIn("Go and see them", result.stdout)

    def test_stickers_are_ignored_silently(self) -> None:
        add_messages(self.export, [
            {"id": 9, "type": "message", "from": "Anna Kowalska", "from_id": "user111",
             "file": "stickers/sticker.webp", "mime_type": "image/webp", "media_type": "sticker", "text": ""},
            {"id": 10, "type": "message", "from": "Anna Kowalska", "from_id": "user111",
             "file": "(File not included. Change data exporting settings to download.)",
             "file_name": "sticker.webp", "mime_type": "image/webp", "media_type": "sticker", "text": ""},
        ], {})
        (self.export / "stickers").mkdir()
        (self.export / "stickers" / "sticker.webp").write_bytes(b"STICKER")
        result = self.sort()
        self.assertFalse(any(p.endswith("sticker.webp") for p in listing(self.out)))
        self.assertIn("1 photo(s)/video(s) were not included in the export", result.stdout)  # only the real photo

    def test_videos_are_copied_gifs_are_not(self) -> None:
        (self.export / "video_files").mkdir()
        (self.export / "round_video_messages").mkdir()
        add_messages(self.export, [
            {"id": 9, "type": "message", "from": "Anna Kowalska", "from_id": "user111",
             "file": "video_files/IMG_0894.MOV", "thumbnail": "video_files/IMG_0894.MOV_thumb.jpg",
             "mime_type": "video/quicktime", "media_type": "video_file", "text": ""},
            {"id": 10, "type": "message", "from": "Anna Kowalska", "from_id": "user111",
             "file": "round_video_messages/file_1.mp4", "mime_type": "video/mp4",
             "media_type": "video_message", "text": ""},
            {"id": 11, "type": "message", "from": "Anna Kowalska", "from_id": "user111",
             "file": "files/raw.mov", "mime_type": "video/quicktime", "text": ""},
            {"id": 12, "type": "message", "from": "Anna Kowalska", "from_id": "user111",
             "file": "video_files/funny.gif.mp4", "mime_type": "video/mp4", "media_type": "animation", "text": ""},
            {"id": 13, "type": "message", "from": "Anna Kowalska", "from_id": "user111",
             "file": "(File not included. Change data exporting settings to download.)",
             "mime_type": "video/mp4", "media_type": "animation", "text": ""},
        ], {
            "video_files/IMG_0894.MOV": b"MOV", "video_files/IMG_0894.MOV_thumb.jpg": b"t",
            "round_video_messages/file_1.mp4": b"ROUND", "files/raw.mov": b"RAW",
            "video_files/funny.gif.mp4": b"GIF",
        })
        result = self.sort()
        files = listing(self.out)
        self.assertTrue({"Anna Kowalska/IMG_0894.MOV", "Anna Kowalska/file_1.mp4", "Anna Kowalska/raw.mov"} <= files)
        self.assertNotIn("Anna Kowalska/funny.gif.mp4", files)
        self.assertNotIn("Anna Kowalska/IMG_0894.MOV_thumb.jpg", files)
        self.assertIn("Copied 4 photo(s) and 3 video(s)", result.stdout)
        self.assertIn("1 photo(s)/video(s) were not included", result.stdout)  # the photo, not the GIF

    def test_same_name_different_accounts_get_ids(self) -> None:
        add_messages(self.export, [
            {"id": 9, "type": "message", "from": "Anna Kowalska", "from_id": "user999",
             "photo": "photos/photo_9.jpg", "text": ""},
        ], {"photos/photo_9.jpg": b"PHOTO-9"})
        self.sort()
        files = listing(self.out)
        self.assertIn("Anna Kowalska (user111)/IMG_4821.jpg", files)
        self.assertIn("Anna Kowalska (user999)/photo_9.jpg", files)
        # Unique names stay plain.
        self.assertIn("Piotr _ Nowak_ Team_/photo_2@02-01-2025_10-12-00.jpg", files)

    def test_renamed_sender_stays_in_one_folder_under_latest_name(self) -> None:
        add_messages(self.export, [
            {"id": 9, "type": "message", "from": "Anna K.", "from_id": "user111",
             "photo": "photos/photo_9.jpg", "text": ""},
        ], {"photos/photo_9.jpg": b"PHOTO-9"})
        self.sort()
        self.assertEqual({p.split("/")[0] for p in listing(self.out)} & {"Anna K", "Anna Kowalska"}, {"Anna K"})

    def test_names_differing_only_in_case_get_ids(self) -> None:
        add_messages(self.export, [
            {"id": 9, "type": "message", "from": "anna kowalska", "from_id": "user999",
             "photo": "photos/photo_9.jpg", "text": ""},
        ], {"photos/photo_9.jpg": b"PHOTO-9"})
        self.sort()
        files = listing(self.out)
        self.assertIn("Anna Kowalska (user111)/IMG_4821.jpg", files)
        self.assertIn("anna kowalska (user999)/photo_9.jpg", files)

    def test_long_file_name_in_prefix_mode_is_shortened(self) -> None:
        long_name = "x" * 250 + ".jpg"
        add_messages(self.export, [
            {"id": 9, "type": "message", "from": "Anna Kowalska", "from_id": "user111",
             "file": f"files/{long_name}", "mime_type": "image/jpeg", "text": ""},
        ], {f"files/{long_name}": b"LONG"})
        self.sort("--mode", "prefix")
        names = [n for n in listing(self.out) if n.startswith("Anna Kowalska__xxx")]
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].endswith(".jpg") and len(names[0].encode()) <= 255)

    def test_dangling_symlink_in_output_is_not_written_through(self) -> None:
        target = Path(self.tmp.name) / "target.jpg"
        (self.out / "Anna Kowalska").mkdir(parents=True)
        os.symlink(target, self.out / "Anna Kowalska" / "IMG_4821.jpg")
        self.sort()
        self.assertFalse(target.exists())
        self.assertIn("Anna Kowalska/IMG_4821_1.jpg", listing(self.out))

    def test_full_account_export_gets_one_folder_per_chat(self) -> None:
        make_account_export(self.export, [OTHER_CHAT], OTHER_CHAT_FILES)
        result = self.sort()
        files = listing(self.out)
        self.assertIn("Test group/Anna Kowalska/IMG_4821.jpg", files)
        self.assertIn("Other group/Zofia Lis/photo_z.jpg", files)
        self.assertIn("[Other group]", result.stdout)

    def test_hostile_group_name_is_sanitized(self) -> None:
        evil = dict(OTHER_CHAT, name="../../‮evil:/..")
        make_account_export(self.export, [evil], OTHER_CHAT_FILES)
        self.sort()
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["Test group", "_.._evil__"])
        self.assertEqual(sorted(p.name for p in Path(self.tmp.name).iterdir()), ["export", "out"])

    def test_paths_outside_export_are_ignored(self) -> None:
        secret = Path(self.tmp.name) / "secret.jpg"
        secret.write_bytes(b"SECRET")
        add_messages(self.export, [
            {"id": 9, "type": "message", "from": "Mallory", "from_id": "user666",
             "photo": "../secret.jpg", "text": ""},
        ], {})
        result = self.sort()
        self.assertNotIn("Mallory/secret.jpg", listing(self.out))
        self.assertIn("1 path(s) in result.json pointed outside", result.stdout)


if __name__ == "__main__":
    unittest.main()
