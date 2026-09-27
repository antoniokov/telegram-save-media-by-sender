# CLAUDE.md

Project brief for Claude Code. Read `README.md` for usage and, under "How it works", the research behind the design.

## What this is

A macOS-oriented tool that takes a Telegram Desktop chat export (`result.json` + `photos/` + `files/`) and sorts every photo and video by sender — one folder per person, or a `Sender__` filename prefix — so photos can be credited when re-posted.

## Layout

- `save_media_by_sender.py` — the whole tool, standard library only, Python 3.8+. Keep it dependency-free unless a feature truly needs a package (perceptual-hash dedupe is the one candidate; make it optional if added).
- `tests/test_save_media_by_sender.py` — builds a synthetic export in a temp dir and runs the script as a subprocess. Run: `python3 -m unittest discover -s tests`.

## Who it's for

Tinkerers who are comfortable in a terminal or with AI coding tools, and who want flags, a clear README and code they can read and adapt. Non-technical people should be able to use it too, which is why the zero-argument path exists. Drop the script into the export folder, run `python3 save_media_by_sender.py` with no arguments, then read where the files went. Keep that path working and make every error message say what to do next in plain words. Don't strip out options or technical detail to serve it.

## Facts to keep in mind

- Only the `photo` and `file` keys of a message carry media. Keep photos and videos (`video_file`, `video_message`, or `video/*` sent as file). `thumbnail` is Telegram's own `<file>_thumb.jpg` preview and must never be copied (this is the "duplicate photos" issue — by design in tdesktop, not a bug).
- Skip stickers, GIFs (`animation`), voice and audio entirely (static stickers are `image/webp`) — neither copied nor reported.
- `type == "service"` messages have no sender; skip them.
- `from` can be `null` (deleted account, anonymous admin); fall back to `from_id`.
- Sender and group names go into paths and are untrusted — sanitize them (see `safe_name`). Paths in `result.json` must resolve inside the export folder.
- Group by `from_id`. Add ` (<from_id>)` only when two accounts share a display name (case-insensitively); there are no usernames in the export.
- Input and output are flags, not positionals. With no `--input`, the export is the folder the script lives in, or else the current folder. With no `--output`, files go to `./output/<sender>/` in the current folder; a full-account export adds a `<chat>/` level in between.
- A missing `result.json` must be explained: an HTML export (`messages.html`, `export_results.html`) means "re-export as Machine-readable JSON"; nothing at all means "copy the script into the export folder or use `--input`".
- The summary ends with the absolute path of the output folder. Keep the per-sender statistics above it.
- Default is copy, not move; the export folder must stay untouched unless `--move`.
- Byte-identical images are deduped by SHA-256 by default; `--keep-duplicates` disables it.
- Placeholder strings like `(File not included. …)` appear where the export size limit excluded a file — count them, don't crash.

## Verifying changes

Add a case to the synthetic export in the test file rather than testing by hand; keep the tests stdlib-only and fast.

## Privacy

`input/` and `output/` hold real chat exports (other people's photos, names, IDs, GPS in EXIF). They are gitignored; never commit them, quote their contents in docs or tests, or use real names from them in examples. Test fixtures use made-up names only.
