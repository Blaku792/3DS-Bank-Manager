# 3DSBank layout verification

Verified against RocketRobz/3DSBank commit
[`5f23dac4f19fc94fdea279f7ea5d251f043ed12c`](https://github.com/RocketRobz/3DSBank/tree/5f23dac4f19fc94fdea279f7ea5d251f043ed12c)
(master as inspected on 2026-11-16). This is the original DS-mode application;
this project is a separate native libctru implementation and does not port its
mutation code.

Source evidence:

- [`arm9/source/main.cpp`](https://github.com/RocketRobz/3DSBank/blob/5f23dac4f19fc94fdea279f7ea5d251f043ed12c/arm9/source/main.cpp),
  `settingsinipath` and `LoadSettings`: `/3DSBank/3DSBank.ini`, section `3DSBANK`,
  `FOLDER_SLOT` (upstream defaults to 0), and `SLOT_NAME_0` through
  `SLOT_NAME_39` (default `Slot N`).
- In the same file, `storeFolder` builds `sd:/3DSBank/Slot%i` and renames
  `sd:/Nintendo 3DS` there. `selectFolder` performs the inverse rename.
- `main` loads settings, calls `storeFolder`, then enumerates stored directories.
  `SaveSettings(true)` temporarily records the number of enumerated directories;
  selecting a bank writes the cursor index before restoring that directory to
  `/Nintendo 3DS`. A snapshot taken while upstream is running can therefore have
  transient metadata. v0.1 does not try to fix or emulate that sequence.
- [`arm9/source/inifile.cpp`](https://github.com/RocketRobz/3DSBank/blob/5f23dac4f19fc94fdea279f7ea5d251f043ed12c/arm9/source/inifile.cpp),
  `LoadIniFile` / `GetFileString` / `GetInt`: INI text, optional UTF-8 BOM,
  whitespace trimming, CR/LF lines, integer slot and string aliases.

Upstream's `sd:` device prefix becomes libctru's `sdmc:`. The SD-relative names
and casing are unchanged. A healthy example after selecting slot 2 is:

```text
/3DSBank/3DSBank.ini       [3DSBANK], FOLDER_SLOT=2
/3DSBank/Slot0/           stored
/3DSBank/Slot1/           stored
/Nintendo 3DS/            selected slot 2
```

`/3DSBank/Slot2` is normally absent in this example. It must not be mistaken for
a missing bank. Conversely, an alias alone does not prove a stored bank exists.

## Conservative discovery rules

v0.1 checks exact `Slot0`…`Slot39` paths as directories and reads optional names.
It enumerates `/3DSBank` once to flag unexpected entries without descending into
them. It does not reproduce upstream's assumption that sorting all directories
and using a cursor index always equals a slot number.

Alias keys must match `SLOT_NAME_0` through `SLOT_NAME_39` exactly after trimming
surrounding whitespace, as upstream constructs them with `to_string(i)`.
Zero-padded keys such as `SLOT_NAME_02` are ignored with a configuration warning;
they cannot replace or suppress `SLOT_NAME_2` regardless of key order. Without a
canonical alias the default `Slot N` remains. An invalid alias alone does not
invalidate a valid `FOLDER_SLOT` selection.

The active slot is labeled `active (INI)` only when there is one valid explicit
`FOLDER_SLOT` in range, `/Nintendo 3DS` is a directory, and the corresponding
stored path is absent. Both paths present (or a stored-path read error) produce
a conflict; no live folder produces an active-missing diagnostic. Invalid,
duplicate, missing, or unreadable active metadata leaves selection unknown with a
configuration warning. There must be exactly one matching section, including
sections with no active key; aliases from later duplicates are not merged.
Unlike upstream's default-to-zero behavior, the scanner does not guess on a
card it will not modify. In particular, a live folder with no INI stays unknown.

Upstream identifies section names through the first `]`, so suffix annotations
such as `[3DSBANK] ; note`, `[3DSBANK] text`, and `[3DSBANK]=annotation` are
recognized. The scanner follows that section-name rule, counts all matching
sections, and leaves the active bank unknown if more than one exists, even if
their keys agree or only the second supplies `FOLDER_SLOT`. A header missing its
closing bracket also invalidates active metadata. Upstream's inner key loop
checks `=` before checking section boundaries, so an `=` annotation on a later
header can also be ambiguous; the scanner flags that instead of inferring a
selection across it. CR and LF independently terminate lines (the LF half of a
CRLF is harmless whitespace); a final unterminated line is parsed normally.

The parser intentionally rejects malformed/trailing-junk slot values, duplicates,
NULs, and oversized lines rather than reproducing permissive `strtol` behavior.
Alias display is bounded and sanitized. Neither a valid INI nor a directory
check verifies encryption, console ownership, saves, or installed titles.

No upstream implementation source is copied into the application. These links
document the observed storage convention; upstream remains credited to its
respective authors and under its own license.
