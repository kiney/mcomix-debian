# MComix Debian package with local patches

This repository is a small, unofficial packaging workspace based on the
[official Debian MComix package](https://tracker.debian.org/pkg/mcomix). It
combines Debian's packaging with the current
[upstream MComix 3.2.0 release](https://sourceforge.net/projects/mcomix/files/MComix-3.2.0/)
and a handful of focused local patches. It is not a separate MComix fork.

## Local patches

- `01_fix_ftbfs.patch` includes the missing `setup.cfg` in the source manifest
  so the package builds correctly.
- `02_ignore_invalid_cached_thumbnails.patch` regenerates cached thumbnails
  whose metadata is missing or invalid instead of failing.
- `03_increase_magnifying_lens_size_limit.patch` raises the maximum magnifying
  lens size to 2000 pixels.
- `04_add_ai_image_tools.patch` adds two OpenAI-compatible tools: ask questions
  about the current image and transform it. Text and image services have
  independent endpoint, API key, model, and timeout settings. Generated images
  are reversible session-only page overrides.
- `05_persist_preferences_on_dialog_close.patch` saves changed preferences as
  soon as the Preferences dialog closes, including the AI configuration.
- `06_support_unrar_free.patch` adds a checked adapter for `unrar-free >= 0.3.0`.
  It reads RAR4/RAR5 listings and extracts selected members in sequential batches,
  including solid RAR5. Files are published only after data lengths and the
  extractor's exit status have been checked. RARLabs extractors and 7z with
  RAR3/RAR5 decoders retain priority; Debian's 7z without its optional RAR
  codecs no longer masks the free fallback. Startup no longer warns about
  `unrar-free` symlinks.

The free fallback inherits libarchive's limitations: encrypted RAR and solid
RAR4 require `unrar`, `libunrar`, or 7z with RAR codecs. Ambiguous newline-bearing
names, conflicting sanitized names, and inconsistent data streams fail explicitly
instead of producing empty or damaged images. The adapter's tests include real
libarchive 3.7.4 RAR fixtures (license retained under `tests/fixtures/`) and can be
run with `python3 -m unittest discover -s tests -p test_unrar_free.py` inside the
source directory. The original upstream tarball remains unchanged.

## AI feature demo

[![AI tools demo](ai_peek.gif)](ai_peek.mp4)

Click the preview to open the original H.264 video.

## Building

The source tree is in `mcomix-3.2.0/`. Build the source package from the
repository root and the binary package from inside the source tree:

```sh
dpkg-source -b mcomix-3.2.0
cd mcomix-3.2.0
dpkg-buildpackage -us -uc -b
```
