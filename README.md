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
docker run --rm -v "$PWD:/project" -w /project devkitpro/devkitarm:latest make -j2
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

The workflow deliberately tracks `devkitpro/devkitarm:latest` to use the maintained
toolchain. For a reproducible local build, use the image digest from that build's
logs. A passing compile verifies the executable format, not behavior on hardware.

## Tests and limitations

Run the host fixture suite with Python 3 and a C compiler, without devkitARM:

```sh
python3 -m unittest discover -s tests -v
```

It compiles the same scanner source with warnings treated as errors and creates
only disposable temporary fixture directories. It checks active/stored slots,
INI aliases, missing paths, malformed/oversized input, unexpected entries, and
compares fixture contents, modes, sizes, and modification times before/after
scans. Do not adapt the tests to a real SD card.

3DS emulators may not expose the physical SD layout or mount `sdmc:` the same way
as Homebrew Launcher. A blank or missing bank list in an emulator does not prove
that a real card has no banks. Fixtures validate discovery logic; they do not
simulate libctru, HOME menu behavior, encryption, title databases, or hardware
permissions. Real-hardware UI/SD validation is a separate manual check: launch,
inspect both screens, browse, rescan, and exit with START. No transfer testing is
part of this release.

Version 0.1 supports upstream's slots 0–39, caps INI reads at 64 KiB and lines at
511 bytes, and stores up to 95 ASCII characters per alias. Longer names are
truncated with a diagnostic; control/non-ASCII bytes display as `?`. Unknown
entries are flagged and not traversed. Missing/invalid active metadata is shown
as unknown; folder presence alone does not identify the active bank. An INI
selection is metadata, not proof of bank identity or integrity.
