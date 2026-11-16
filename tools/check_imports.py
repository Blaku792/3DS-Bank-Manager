"""Fail closed on new application imports; inspect objects, not libctru internals.

This is a regression guard, not a proof about transitive library behavior.
fopen's rb/path arguments are also checked in the host fixture harness.
"""
import argparse
import subprocess

SCANNER = set("""
closedir fclose ferror fgetc fopen opendir readdir stat
memset snprintf strchr strcmp strlen strncmp strtol
__ctype_b_loc __errno_location _ctype_ __errno
""".split())
UI = set("""
aptMainLoop banks_scan banks_status consoleClear consoleInit consoleSelect
 gfxExit gfxFlushBuffers gfxInitDefault gfxSwapBuffers gspWaitForEvent
hidKeysDown hidScanInput printf puts strlen
""".split())


def check(nm, path, allowed):
    output = subprocess.check_output([nm, "-u", str(path)], text=True)
    imports = {line.split()[-1] for line in output.splitlines() if line.strip()}
    extra = imports - allowed
    if extra:
        raise ValueError(f"{path}: unapproved imports: {', '.join(sorted(extra))}")
    return imports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nm", default="nm")
    parser.add_argument("--scanner", required=True)
    parser.add_argument("--ui")
    args = parser.parse_args()
    check(args.nm, args.scanner, SCANNER)
    if args.ui:
        check(args.nm, args.ui, UI)
    print("Application import allowlist passed")
