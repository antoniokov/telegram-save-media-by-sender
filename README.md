Save every photo and video from a Telegram group to your computer, organized by who sent it, so you can credit the author when you post on social media.

```
output/
├── Christina/
│   ├── art002e009288.jpg
│   ├── art002e009289.jpg
│   └── art002e009294.jpg
├── Jeremy/
│   ├── art002e012093.jpg
│   ├── art002e012702.jpg
├── Reid/
│   ├── art002e000190.jpg
│   ├── art002e000192.jpg
└── Victor/
    ├── art002e010208.jpg
    ├── art002e010232.jpg
    └── art002e014066.jpg
```

It's a single Python script with no dependencies. It runs offline: nothing is uploaded anywhere, and your Telegram export is left untouched.

## Requirements

- **Python 3.8 or newer.** macOS: run `python3 --version` in Terminal. If Python is missing, macOS offers to install the Command Line Tools, which include it.
- **Telegram Desktop**, used to export the chat. On macOS, this is *not* the App Store app called "Telegram", which can't export. Get it from [desktop.telegram.org](https://desktop.telegram.org/). "Telegram Lite" from the App Store also works, but it has had a bug where you can't choose the export format ([tdesktop #25940](https://github.com/telegramdesktop/tdesktop/issues/25940)).

## Usage

1. **Export the chat.** In Telegram Desktop, open the group → **⋮** menu → **Export chat history**:
   - tick **Photos** and **Videos**, plus **Files** if people send pictures uncompressed ("as file")
   - set the format to **Machine-readable JSON**
   - raise the size limit so that large videos are included
   - export. You get a folder like `~/Downloads/Telegram Desktop/ChatExport_2026-09-26` that holds `result.json`.
2. **Put the script into that folder.** Open [`save_media_by_sender.py`](save_media_by_sender.py) on GitHub, click the **Download raw file** button (the arrow icon above the code), and move the downloaded file next to `result.json`.
3. **Run it.** Open Terminal, type `cd ` (with a space after it), drag the export folder from Finder into the Terminal window, and press Enter. Then:

   ```bash
   python3 save_media_by_sender.py
   ```

   The script prints how many photos and videos each person sent, anything it had to skip, and where the sorted files are: a new `output/` folder with one subfolder per sender.

### Options

Without arguments, the script looks for `result.json` next to itself first, then in the folder you run it from, and writes to `output/` in the folder you run it from. Both can be changed:

```bash
python3 save_media_by_sender.py --input ~/Downloads/Telegram\ Desktop/ChatExport_2026-09-26   # the export is elsewhere
python3 save_media_by_sender.py --output ~/Pictures/Hiking\ Club   # choose where the sorted files go
python3 save_media_by_sender.py --mode prefix                     # one flat folder: "Christina__art002e009288.jpg"
python3 save_media_by_sender.py --move                            # move instead of copy (changes the export folder)
python3 save_media_by_sender.py --keep-duplicates                 # keep byte-identical repeats
```

`-i` and `-o` are short forms of `--input` and `--output`.

A full-account export (Settings → Advanced → **Export Telegram data**) also works. Each chat then gets its own folder: `output/<Chat>/<Sender>/`.

## What gets copied

Copied:

- Photos (Telegram's compressed version)
- Images sent as files, at original quality (JPG, PNG, HEIC, …)
- Videos and round video messages

Skipped:

- Stickers and GIFs (they come from sticker packs and GIF search, not from the sender)
- Voice messages, music, documents
- Telegram's `*_thumb.jpg` preview files
- Exact duplicates, such as the same file forwarded twice

## Good to know

- **Two people with the same name** get separate folders with their account IDs added: `Anna (user111)/` and `Anna (user222)/`. Someone who changed their name during the chat stays in one folder, under their latest name.
- **Photos sent the normal way are compressed by Telegram.** Only images sent as files come back at full quality.
- **If a photo shows up as "not included"** in the summary, the export size limit left it out. Re-export with a higher limit.
- **If the script complains about `messages.html`,** the chat was exported as HTML. Export again with the format set to Machine-readable JSON.
- **Anonymous admin posts** are attributed to the group, not to a person.

## Privacy

Your export and the sorted output contain other people's photos, names and account IDs. Photos sent as files often still carry the location where they were taken. Keep them to yourself unless the senders agree. If you fork this repository, the `.gitignore` already excludes `input/`, `output/`, `ChatExport_*/` and `result.json`, so exports don't end up in a commit by accident.

The script treats the export as untrusted input. Sender and group names are cleaned before they're used as folder names, and it refuses to read files outside the export folder.

## Development

```bash
python3 -m unittest discover -s tests
```

The tests build a small fake export in a temp folder, so no real chat data is needed.

## How it works

Background for contributors: what a Telegram Desktop export looks like, and why the script behaves the way it does.

### Export layout (verified against tdesktop source)

`result.json` has one object per message. Relevant keys ([schema](https://core.telegram.org/import-export)):

| key | meaning |
|---|---|
| `type` | `"message"` or `"service"` (pins, joins — ignored) |
| `from`, `from_id` | sender display name and `user<id>` / `channel<id>` |
| `photo` | relative path of a compressed photo → `photos/photo_<n>@DD-MM-YYYY_hh-mm-ss.jpg` |
| `file`, `mime_type`, `file_name` | any document: videos → `video_files/…`, round videos → `round_video_messages/…`, anything sent "as file" → `files/…` |
| `media_type` | `video_file`, `video_message` (kept); `sticker`, `animation` (GIF), `voice_message`, `audio_file` (skipped); absent for files |
| `thumbnail` | Telegram's own small preview of a document, saved as `<file>_thumb.jpg` |

Full-account exports wrap chats in `chats.list[]`; the script handles both shapes.

`from` can be `null` (deleted account, anonymous admin); the script falls back to `from_id`. Where the export size limit excluded a file, the path is replaced by a placeholder like `(File not included. Change data exporting settings to download.)`. These are counted and reported.

An HTML export has no `result.json`; it holds `messages.html` (or `export_results.html` for a full account). The script recognises that and asks for a JSON export instead of failing with a bare "file not found".

### Senders with the same name

Images are grouped by `from_id`, not by display name, so two people called "Anna" never share a folder, and someone who renamed mid-chat stays in one folder under their latest name. Only when two accounts have the same name (compared case-insensitively, because macOS and Windows file systems are) are IDs added: `Anna (user111)/`, `Anna (user222)/`. The export has no usernames for message senders (only `from` and `from_id`), so the ID is the only thing that tells them apart.

### Untrusted input

Group and sender names come from other people, so the script cleans them before using them in paths:

- drops control and invisible characters, including right-to-left overrides that can disguise a name
- replaces `/ \ : * ? " < > |`
- strips leading and trailing dots, so `.` and `..` can't occur
- caps names at 100 bytes, and shortens file names in prefix mode to fit the 255-byte limit

Paths in `result.json` that resolve outside the export folder (including through symlinks) are ignored. Existing files in the output folder are never overwritten; a numeric suffix is added instead, and dangling symlinks count as existing.

### Duplicates

- **Every image sent as a file gets a `<name>_thumb.jpg` twin.** This is by design in Telegram Desktop (`export_data_types.cpp`: `suggestedPath = documentPath + "_thumb.jpg"`), used for the HTML export and written for JSON too. The script never copies `thumbnail` entries or `*_thumb.jpg` paths.
- **Byte-identical repeats** (forwards, re-posts of the same file) are skipped via SHA-256; `--keep-duplicates` disables that.
- **Not handled yet:** the same picture posted once as a photo and once as a file. The bytes differ (Telegram recompresses photos), so it would need perceptual hashing (e.g. `Pillow` + `imagehash`), added as an optional dependency.

## License

[MIT](LICENSE)
