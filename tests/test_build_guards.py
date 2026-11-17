"""Exercise artifact validation and the fail-closed application import allowlist."""
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from tools.check_imports import SCANNER, check
from tools.validate_artifacts import SMDH_SIZE, validate

REPO = Path(__file__).resolve().parents[1]


class ImportAllowlist(unittest.TestCase):
    def test_scanner_imports_are_allowlisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj = Path(tmp) / "banks.o"
            subprocess.run([os.environ.get("HOST_CC", "cc"), "-std=c11", "-Wall", "-Wextra",
                            "-Werror", "-fno-builtin", "-fstack-protector-strong", "-I", str(REPO / "include"),
                            "-c", str(REPO / "source/banks.c"), "-o", str(obj)], check=True)
            imports = check("nm", obj, SCANNER)
            self.assertIn("fopen", imports)

    def test_new_write_import_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "write.c"
            obj = Path(tmp) / "write.o"
            source.write_text('#include <stdio.h>\nint accidental(const char *p) { return remove(p); }\n')
            subprocess.run([os.environ.get("HOST_CC", "cc"), "-c", str(source), "-o", str(obj)], check=True)
            with self.assertRaisesRegex(ValueError, "unapproved imports: remove"):
                check("nm", obj, SCANNER)


class ArtifactValidation(unittest.TestCase):
    def setUp(self):
        self.metadata = b"SMDH" + bytes(SMDH_SIZE - 4)
        self.executable = bytearray(struct.pack("<4sHH9I", b"3DSX", 44, 8, 0, 0,
                                               4, 0, 0, 0, 72, SMDH_SIZE, 0)
                                    + bytes(24) + bytes(4) + self.metadata)

    def test_valid_pair(self):
        validate(self.executable, self.metadata)

    def test_invalid_smdh_magic_size_and_version(self):
        for metadata in [b"bad!" + self.metadata[4:], self.metadata[:-1],
                         self.metadata[:4] + b"\1" + self.metadata[5:]]:
            with self.subTest(size=len(metadata), prefix=metadata[:8]):
                with self.assertRaises(ValueError):
                    validate(self.executable, metadata)

    def test_invalid_3dsx_header(self):
        for index, value in [(0, 0), (4, 32), (6, 4), (8, 1), (12, 1), (40, 1)]:
            with self.subTest(index=index):
                damaged = self.executable.copy()
                damaged[index] = value
                with self.assertRaises(ValueError):
                    validate(damaged, self.metadata)

    def test_invalid_segment_and_metadata_bounds(self):
        for offset, value in [(16, 0), (16, 0xFFFFFFFC), (20, 1), (28, 4),
                              (32, 71), (36, 1), (44, 0xFFFFFFFF)]:
            with self.subTest(offset=offset):
                damaged = self.executable.copy()
                struct.pack_into("<I", damaged, offset, value)
                with self.assertRaises(ValueError):
                    validate(damaged, self.metadata)

    def test_truncated_trailing_and_mismatched_files(self):
        for damaged in [self.executable[:43], self.executable[:-1], self.executable + b"x",
                        self.executable[:-1] + b"x"]:
            with self.assertRaises(ValueError):
                validate(damaged, self.metadata)

    def test_out_of_bounds_relocation(self):
        damaged = self.executable.copy()
        struct.pack_into("<I", damaged, 44, 1)
        struct.pack_into("<I", damaged, 32, 76)
        damaged[72:72] = struct.pack("<HH", 0, 2)  # code segment has just one word
        with self.assertRaisesRegex(ValueError, "relocation exceeds"):
            validate(damaged, self.metadata)
