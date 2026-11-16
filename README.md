# 3DSBank Manager v0.1

An experimental **read-only** native Nintendo 3DS homebrew slot scanner, written
in C with devkitARM and libctru. This is **NOT a transfer tool**. It cannot move
games, switch banks, install titles, or repair data.

The top screen shows SD/layout/metadata diagnostics. The bottom screen shows all
40 supported slot numbers, their configured names, and whether each is stored,
active according to the INI, absent, conflicting, or unreadable. Absent rows are
shown for context; they are not reported as detected banks.

- **UP / DOWN:** browse slots (eight per page).
- **X:** rescan using read-only operations.
- **START:** exit to the Homebrew Launcher.

## Safety scope

The application only reads directory names, directory metadata, and
`sdmc:/3DSBank/3DSBank.ini`. It does not traverse the contents of any bank or
`Nintendo 3DS`, open games/saves/title databases, access NAND, use AM, create
folders, rename files, delete files, or write configuration/logs to the SD card.
Console output goes to the screens. All scan state lives in RAM.

Do not run 3DSBank concurrently with this scanner. This is a snapshot, not a
transaction or a validation of game data. Diagnostics never trigger repairs.
The app remains read-only even when metadata is missing or inconsistent.

## Verified 3DSBank layout

See [upstream verification](docs/UPSTREAM.md) for pinned source links and the
active-bank rules. In brief, stored slots are `/3DSBank/Slot0` through `Slot39`;
the selected bank normally resides at `/Nintendo 3DS`, outside that directory.
Names and the selected slot are recorded in `/3DSBank/3DSBank.ini`.
Do not create a guessed directory layout on your real card for this application.

## Build

Install the maintained [devkitPro toolchain](https://devkitpro.org/wiki/Getting_Started)
and the `3ds-dev` package group (devkitARM, libctru, and 3DS tools). With the normal
devkitPro environment configured:

```sh
export DEVKITPRO=/opt/devkitpro
export DEVKITARM="$DEVKITPRO/devkitARM"
export PATH="$DEVKITPRO/tools/bin:$DEVKITARM/bin:$PATH"
make -j2
```

Alternatively use the same maintained official container as CI:

```sh
docker run --rm -v "$PWD:/project" -w /project devkitpro/devkitarm@sha256:116afba8df8453961de2936ffab20dd441edf4d682856c1ec8b0e53d7ed0bbf5 make -j2
```

Outputs: `3DSBankManager.3dsx`, `3DSBankManager.smdh`, and a debug ELF.
`make clean` removes generated outputs. Build-time file writes occur only in
the checkout; the application's runtime read-only guarantee concerns the 3DS SD.

GitHub Actions runs host tests and compiles the application on pushes, pull
requests, and manual dispatch. After a successful build, open **Actions → Build
and test v0.1 → run → Artifacts → 3DSBankManager-v0.1** and download the ZIP.
Extract it and copy the `.3dsx` and `.smdh` into a directory such as
`/3ds/3DSBankManager/` using your computer, then launch with Homebrew Launcher.
There is no CIA installer in v0.1.

The workflow pins the official devkitPro container by digest and GitHub Actions
by commit SHA. Update these pins deliberately and re-run validation when upgrading.
Host tests and ASan/UBSan must pass before the build job can start. Both jobs check
out the exact source commit (the PR head for pull requests). Before publication,
CI checks application object imports against an allowlist and validates 3DSX
headers, segment/relocation bounds, and embedded/external SMDH consistency.

The ZIP also contains `SOURCE.txt` (source commit, repository, build URL and
container digest) and `SHA256SUMS`. After extracting, verify it with
`sha256sum -c SHA256SUMS`. The commit and checksums are also published in the
Actions run summary. These checks establish artifact structure and provenance;
they do not execute the app or prove hardware compatibility.

## Tests and limitations

Run the host suite with Python 3, a C compiler, GNU ld wrapping and `nm`
(on Linux), without devkitARM:

```sh
python3 -m unittest discover -s tests -v
```

It compiles the same scanner source with warnings treated as errors and creates
only disposable temporary fixture directories. It checks active/stored slots,
INI aliases, missing paths, malformed/oversized input, unexpected entries, and
compares fixture contents, modes, sizes, and modification times before/after
scans. Test-only wrappers inject permission/read failures independent of the
host user's privileges, enforce `fopen`'s read-only mode and configuration path,
and reproduce numeric overflow immediately before directory EOF. Repeated scans
reuse one result structure. The import allowlist rejects new application APIs,
including filesystem writes, and includes a negative test using `remove`.
This is a regression guard, not a proof about transitive library behavior.
Do not adapt the tests to a real SD card.

Run the same suite with sanitizers (supported GCC/Linux hosts):

```sh
HOST_CFLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer -g -fno-pie -no-pie' \
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
python3 -m unittest discover -s tests -v
```

LeakSanitizer cannot run under ptrace/tracing sandboxes. Use an untraced host,
or disable leak detection there while retaining AddressSanitizer and UBSan.
CI runs with leak detection enabled. To validate locally built output:

```sh
python3 tools/check_imports.py --nm "$DEVKITARM/bin/arm-none-eabi-nm" --scanner build/banks.o --ui build/main.o
python3 tools/validate_artifacts.py 3DSBankManager.3dsx 3DSBankManager.smdh
```

3DS emulators may not expose the physical SD layout or mount `sdmc:` the same way
as Homebrew Launcher. A blank or missing bank list in an emulator does not prove
that a real card has no banks. Fixtures validate discovery logic; they do not
simulate libctru, HOME menu behavior, encryption, title databases, or hardware
permissions. The next milestone is Azahar emulator testing and another successful
review before controlled New Nintendo 3DS hardware testing. Neither emulator nor
hardware testing has been performed for these corrections. Future UI/SD checks
should cover both screens, browsing, rescanning, and START exit. No transfer
testing is part of this release.

Version 0.1 supports upstream's slots 0–39, caps INI reads at 64 KiB and lines at
511 bytes, and stores up to 95 ASCII characters per alias. Reaching the 64 KiB
read limit invalidates active metadata conservatively, including a file exactly
that size. Longer names are
truncated with a diagnostic; control/non-ASCII bytes display as `?`. Unknown
entries are flagged and not traversed. Missing/invalid active metadata is shown
as unknown with a configuration warning; folder presence alone does not identify
the active bank. Headers such as `[3DSBANK] ; note` are supported, as are CR, LF,
CRLF, and unterminated final lines. Duplicate matching sections (even empty ones)
or duplicate active keys invalidate selection instead of choosing a section. An INI
selection is metadata, not proof of bank identity or integrity.
