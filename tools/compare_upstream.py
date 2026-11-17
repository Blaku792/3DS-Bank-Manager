"""Opt-in host comparison with the pinned, unmodified original 3DSBank INI parser.

Supply a local directory containing inifile.cpp/.h and stringtool.cpp/.h from
RocketRobz/3DSBank commit 5f23dac4f19fc94fdea279f7ea5d251f043ed12c, arm9/source.
This script does not download or vendor upstream code. It verifies source hashes,
builds in temporary storage, and runs only GetInt and this project's scanner
against synthetic INIs. It never runs upstream main or calls a save method.

Requires Python 3, a Linux C/C++ compiler and GNU ld --wrap support. The compiler
alias vasiprintf=vasprintf adapts newlib's integer formatter to the host; unsigned
char matches the original ARM build's byte/BOM comparisons. Source files remain
unchanged. Upstream GetInt may update defaults in RAM; fopen/fwrite guards reject
disk writes. This is a comparison harness, not an emulator or hardware test.
"""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

PINNED_COMMIT = "5f23dac4f19fc94fdea279f7ea5d251f043ed12c"
SOURCE_HASHES = {
    "inifile.cpp": "e56bd4c61ef8b9ac79246d771fee698c4581acd21467a67f3268e1e8dc0bccd9",
    "inifile.h": "99f1cb92ec72ba9752a8e16df867b824b80d8729c8ad734007c3a5f34c04c571",
    "stringtool.cpp": "45ac0fed0a9989a1bd6e217011c60e9c3c378b2c109550b51106015d8e91d34c",
    "stringtool.h": "6ae1833b7448a708839105137dd0c1144ca7ac2269fa638e4b20270f787f0b30",
}
REPO = Path(__file__).resolve().parents[1]

UPSTREAM_HARNESS = r'''
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "inifile.h"

static const char *allowed_path;
extern "C" FILE *__real_fopen(const char *, const char *);
extern "C" FILE *__wrap_fopen(const char *path, const char *mode) {
    if (std::strcmp(path, allowed_path) || std::strcmp(mode, "rb")) std::abort();
    return __real_fopen(path, mode);
}
extern "C" size_t __wrap_fwrite(const void *, size_t, size_t, FILE *) {
    std::abort();
}
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    allowed_path = argv[1];
    CIniFile ini(allowed_path);
    std::printf("%d\n", ini.GetInt("3DSBANK", "FOLDER_SLOT", 0));
    return 0;
}
'''


def cases():
    """Each row declares expected upstream value, manager selection and warnings."""
    rows = [
        ("spaces", b" [3DSBANK] \n FOLDER_SLOT = 2 \n", 2, 2, 0),
        ("tabs", b"\t[3DSBANK]\t\n\tFOLDER_SLOT\t=\t2\t\n", 2, 2, 0),
        ("CR", b"[3DSBANK]\rFOLDER_SLOT=2\r", 2, 2, 0),
        ("LF", b"[3DSBANK]\nFOLDER_SLOT=2\n", 2, 2, 0),
        ("CRLF", b"[3DSBANK]\r\nFOLDER_SLOT=2\r\n", 2, 2, 0),
        ("unterminated", b"[3DSBANK]\nFOLDER_SLOT=2", 2, 2, 0),
        ("BOM", b"\xef\xbb\xbf[3DSBANK]\nFOLDER_SLOT=2\n", 2, 2, 0),
        ("annotated-header", b"[3DSBANK] ; note\nFOLDER_SLOT=2\n", 2, 2, 0),
    ]
    for name, control in [("VT", b"\x0b"), ("FF", b"\x0c")]:
        rows.extend([
            (name + "-after-key", b"[3DSBANK]\nFOLDER_SLOT" + control + b"=2\n", 0, -1, 2),
            (name + "-before-key", b"[3DSBANK]\n" + control + b"FOLDER_SLOT=2\n", 0, -1, 2),
            (name + "-before-header", control + b"[3DSBANK]\nFOLDER_SLOT=2\n", 0, -1, 2),
            (name + "-inside-header", b"[3DSBANK" + control + b"]\nFOLDER_SLOT=2\n", 0, -1, 2),
            (name + "-after-header", b"[3DSBANK]" + control + b"\nFOLDER_SLOT=2\n", 2, -1, 2),
            (name + "-later-boundary", b"[3DSBANK]\nFOLDER_SLOT=2\n" + control +
             b"[OTHER]\nFOLDER_SLOT=3\n", 2, -1, 2),
        ])
    rows.extend([
        ("bad-alias-key-after-selection", b"[3DSBANK]\nFOLDER_SLOT=2\nSLOT_NAME_2\x0b=Alias\n", 2, -1, 2),
        ("duplicate-keys", b"[3DSBANK]\nFOLDER_SLOT=2\nFOLDER_SLOT=3\n", 2, -1, 2),
        ("empty-first-section", b"[3DSBANK]\n[3DSBANK]\nFOLDER_SLOT=2\n", 0, -1, 2),
        ("duplicate-agreeing-sections", b"[3DSBANK]\nFOLDER_SLOT=2\n[3DSBANK]\nFOLDER_SLOT=2\n", 2, -1, 2),
        ("nonnumeric-value", b"[3DSBANK]\nFOLDER_SLOT=abc\n", 0, -1, 2),
        ("trailing-value-junk", b"[3DSBANK]\nFOLDER_SLOT=2junk\n", 2, -1, 2),
        ("negative-value", b"[3DSBANK]\nFOLDER_SLOT=-1\n", -1, -1, 2),
        ("VT-before-value", b"[3DSBANK]\nFOLDER_SLOT=\x0b2\n", 2, -1, 2),
        ("VT-after-value", b"[3DSBANK]\nFOLDER_SLOT=2\x0b\n", 2, -1, 2),
    ])
    return rows


def snapshot(root):
    return [(p.relative_to(root).as_posix(), p.stat().st_mode, p.stat().st_mtime_ns,
             p.stat().st_ctime_ns, p.read_bytes() if p.is_file() else None)
            for p in [root, *sorted(root.rglob("*"))]]


def compare(source_dir):
    sources = {}
    for name, expected in SOURCE_HASHES.items():
        data = (source_dir / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"{name}: does not match pinned upstream {PINNED_COMMIT}")
        sources[name] = data

    with tempfile.TemporaryDirectory(prefix="bank-upstream-comparison-") as temp:
        work = Path(temp)
        for name, data in sources.items():
            (work / name).write_bytes(data)
        (work / "reader.cpp").write_text(UPSTREAM_HARNESS)
        upstream = work / "upstream-reader"
        manager = work / "manager-reader"
        subprocess.run([os.environ.get("HOST_CXX", "c++"), "-std=c++11", "-funsigned-char",
                        "-Dvasiprintf=vasprintf", str(work / "reader.cpp"),
                        str(work / "inifile.cpp"), str(work / "stringtool.cpp"),
                        "-Wl,--wrap=fopen", "-Wl,--wrap=fwrite", "-o", str(upstream)], check=True)
        subprocess.run([os.environ.get("HOST_CC", "cc"), "-std=c11", "-Wall", "-Wextra",
                        "-Werror", "-I", str(REPO / "include"), str(REPO / "source/banks.c"),
                        str(REPO / "tests/scan_cli.c"), str(REPO / "tests/fs_faults.c"),
                        *["-Wl,--wrap=" + name for name in
                          ["fopen", "stat", "opendir", "readdir", "fgetc", "ferror"]],
                        "-o", str(manager)], check=True)
        results = []
        for index, (name, data, expected_upstream, expected_active, expected_warnings) in enumerate(cases()):
            fixture = work / f"fixture-{index}"
            (fixture / "3DSBank").mkdir(parents=True)
            (fixture / "Nintendo 3DS").mkdir()
            ini = fixture / "3DSBank/3DSBank.ini"
            ini.write_bytes(data)
            before = snapshot(fixture)
            original = int(subprocess.check_output([str(upstream), str(ini)], text=True))
            if snapshot(fixture) != before:
                raise ValueError(f"{name}: upstream reader changed fixture")
            output = subprocess.check_output([str(manager), str(fixture)], text=True,
                                             env={**os.environ, "BANK_TEST_FAULT": ""})
            if snapshot(fixture) != before:
                raise ValueError(f"{name}: manager changed fixture")
            fields = dict(item.split("=") for item in output.splitlines()[0].split())
            actual = (original, int(fields["active"]), int(fields["warnings"]))
            expected = (expected_upstream, expected_active, expected_warnings)
            passed = actual == expected
            results.append(passed)
            print(f"{name}: upstream={actual[0]} manager={actual[1]} warnings={actual[2]} "
                  f"{'PASS' if passed else 'FAIL expected ' + repr(expected)}")
        print(f"{sum(results)}/{len(results)} comparisons passed; upstream {PINNED_COMMIT}")
        return all(results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path, help="local pinned arm9/source directory")
    args = parser.parse_args()
    try:
        raise SystemExit(0 if compare(args.source_dir) else 1)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"comparison failed: {error}\n")
