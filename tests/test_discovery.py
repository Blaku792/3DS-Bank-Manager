"""Host fixtures only. Never point this test suite at a real SD card."""
import hashlib
import os
import shlex
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


class Discovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="bank-host-")
        cls.exe = Path(cls.build.name) / "scan"
        subprocess.run([os.environ.get("HOST_CC", "cc"), "-std=c11", "-Wall", "-Wextra",
                        "-Werror", *shlex.split(os.environ.get("HOST_CFLAGS", "")), "-I", str(REPO / "include"), str(REPO / "source/banks.c"),
                        str(REPO / "tests/scan_cli.c"), str(REPO / "tests/fs_faults.c"),
                        *["-Wl,--wrap=" + name for name in
                          ["fopen", "stat", "opendir", "readdir", "fgetc", "ferror"]],
                        "-o", str(cls.exe)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bank-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def directory(self, path):
        (self.root / path).mkdir(parents=True, exist_ok=True)

    def config(self, data):
        self.directory("3DSBank")
        (self.root / "3DSBank/3DSBank.ini").write_bytes(data.encode())

    def snapshot(self):
        return [(str(p.relative_to(self.root)), p.stat().st_mode,
                 p.stat().st_mtime_ns, p.stat().st_size if p.is_file() else 0,
                 hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "")
                for p in sorted(self.root.rglob("*"))]

    def scan(self, root=None, fault=None):
        before = self.snapshot()
        result = subprocess.run([str(self.exe), str(root or self.root)],
                                capture_output=True, text=True,
                                env={**os.environ, "BANK_TEST_FAULT": fault or ""})
        self.assertEqual(result.returncode, 0, result.stderr)
        result = result.stdout.splitlines()
        self.assertEqual(before, self.snapshot(), "scanner changed fixture contents or metadata")
        header = dict(item.split("=") for item in result[0].split())
        self.meta = {key: int(value) for key, value in header.items()}
        self.rows = {int(row.split("|", 2)[0]): row.split("|", 2)[1:] for row in result[1:]}

    def test_normal_active_not_in_bank_directory(self):
        self.config("\ufeff[3DSBANK]\r\nFOLDER_SLOT = 2\r\nSLOT_NAME_2 = Main\r\nSLOT_NAME_10=Archive\r\n")
        self.directory("Nintendo 3DS")
        for n in [0, 10, 39]:
            self.directory(f"3DSBank/Slot{n}")
        self.scan()
        self.assertEqual(self.meta, dict(active=2, stored=3, warnings=0, config=1, root=1, live=1))
        self.assertEqual(self.rows[2], ["Main", "active (INI)"])
        self.assertEqual(self.rows[10], ["Archive", "stored"])
        self.assertEqual(self.rows[1][1], "absent")

    def test_missing_config_does_not_guess_active_zero(self):
        self.directory("Nintendo 3DS")
        self.directory("3DSBank/Slot5")
        self.scan()
        self.assertEqual(self.meta["active"], -1)
        self.assertTrue(self.meta["warnings"] & 2)
        self.assertEqual(self.rows[0][1], "absent")

    def test_empty_card_remains_empty(self):
        self.scan()
        self.assertEqual(self.meta["stored"], 0)
        self.assertEqual(self.meta["active"], -1)
        self.assertFalse(list(self.root.iterdir()))

    def test_missing_sd(self):
        self.scan(self.root / "missing")
        self.assertEqual(self.meta["root"], 0)
        self.assertTrue(self.meta["warnings"] & 1)

    def test_conflict_and_missing_live_folder(self):
        self.config("[3DSBANK]\nFOLDER_SLOT=3\n")
        self.directory("3DSBank/Slot3")
        self.scan()
        self.assertEqual(self.rows[3][1], "CONFLICT")
        self.assertEqual(self.meta["warnings"] & 12, 12)

    def test_missing_active_is_reported(self):
        self.config("[3DSBANK]\nFOLDER_SLOT=0\n")
        self.scan()
        self.assertEqual(self.rows[0][1], "active missing")

    def test_invalid_active_values(self):
        for value in ["-1", "40", "9999999999999999999999", "abc", "2junk", ""]:
            with self.subTest(value=value):
                self.config(f"[3DSBANK]\nFOLDER_SLOT={value}\n")
                self.scan()
                self.assertEqual(self.meta["active"], -1)

    def test_duplicate_active_is_uncertain(self):
        self.config("[3DSBANK]\nFOLDER_SLOT=2\nFOLDER_SLOT=3\n")
        self.scan()
        self.assertEqual(self.meta["active"], -1)

    def test_wrong_section_and_name_sanitizing(self):
        self.config("[OTHER]\nFOLDER_SLOT=2\n[3DSBANK]\nSLOT_NAME_1=Hi\x1b[2J\t!\n")
        self.scan()
        self.assertEqual(self.meta["active"], -1)
        self.assertEqual(self.rows[1][0], "Hi?[2J?!")

    def test_only_canonical_slots_and_directories(self):
        self.config("[3DSBANK]\nFOLDER_SLOT=0\n")
        self.directory("Nintendo 3DS")
        for name in ["Slot01", "Slot40", "slot2", "Other"]:
            self.directory(f"3DSBank/{name}")
        (self.root / "3DSBank/Slot4").write_text("not a directory")
        self.directory("3DSBank/Slot9")
        self.scan()
        self.assertEqual(self.meta["stored"], 1)
        self.assertTrue(self.meta["warnings"] & 32)
        self.assertEqual(self.rows[4][1], "not directory")

    def test_oversize_and_nul_metadata(self):
        for body in ["SLOT_NAME_2=" + "A" * 700, "SLOT_NAME_2=x\0y", ";" * 66000]:
            self.config("[3DSBANK]\nFOLDER_SLOT=2\n" + body + "\n")
            self.scan()
            self.assertEqual(self.meta["active"], -1)
            self.assertTrue(self.meta["warnings"] & 16)

    def test_long_alias_truncation(self):
        self.config("[3DSBANK]\nFOLDER_SLOT=2\nSLOT_NAME_2=" + "A" * 200 + "\n")
        self.scan()
        self.assertEqual(len(self.rows[2][0]), 95)
        self.assertTrue(self.meta["warnings"] & 16)

    def test_directory_instead_of_ini(self):
        self.directory("3DSBank/3DSBank.ini")
        self.scan()
        self.assertEqual(self.meta["active"], -1)
        self.assertTrue(self.meta["warnings"] & 1)

    def healthy(self):
        self.directory("Nintendo 3DS")
        self.config("[3DSBANK]\nFOLDER_SLOT=2\nSLOT_NAME_2=Main\n")

    def assert_unknown(self):
        self.assertEqual(self.meta["active"], -1)
        self.assertTrue(self.meta["warnings"] & 2)
        self.assertFalse(any(row[1] == "active (INI)" for row in self.rows.values()))

    def test_duplicate_sections_with_selection_only_in_second(self):
        self.directory("Nintendo 3DS")
        self.config("[3DSBANK]\nSLOT_NAME_2=First\n[3DSBANK]\nFOLDER_SLOT=2\n")
        self.scan()
        self.assert_unknown()

    def test_duplicate_empty_matching_section(self):
        self.healthy()
        self.config("[3DSBANK]\nFOLDER_SLOT=2\n[OTHER]\n[3DSBANK]\n")
        self.scan()
        self.assert_unknown()

    def test_duplicate_sections_with_same_or_conflicting_selection(self):
        self.directory("Nintendo 3DS")
        for value in [2, 3]:
            with self.subTest(value=value):
                self.config(f"[3DSBANK]\nFOLDER_SLOT=2\n[3DSBANK]\nFOLDER_SLOT={value}\n")
                self.scan()
                self.assert_unknown()

    def test_annotated_headers_recognized_through_closing_bracket(self):
        self.directory("Nintendo 3DS")
        for suffix in [" ; note", " # note", " arbitrary annotation", "=annotation"]:
            with self.subTest(suffix=suffix):
                self.config(f" [3DSBANK]{suffix}\nFOLDER_SLOT=2\nSLOT_NAME_2=Main\n")
                self.scan()
                self.assertEqual(self.meta["warnings"], 0)
                self.assertEqual(self.rows[2], ["Main", "active (INI)"])

    def test_annotated_then_plain_duplicate_is_unknown(self):
        self.healthy()
        self.config("[3DSBANK] ; first\nFOLDER_SLOT=2\n[3DSBANK]\nFOLDER_SLOT=3\n")
        self.scan()
        self.assert_unknown()

    def test_plain_then_annotated_duplicate_is_unknown(self):
        self.healthy()
        self.config("[3DSBANK]\nFOLDER_SLOT=2\n[3DSBANK] ; second\n")
        self.scan()
        self.assert_unknown()

    def test_malformed_header_invalidates_selection(self):
        self.healthy()
        self.config("[3DSBANK]\nFOLDER_SLOT=2\n[3DSBANK\nFOLDER_SLOT=3\n")
        self.scan()
        self.assert_unknown()

    def test_annotated_other_section_ends_matching_section(self):
        self.healthy()
        self.config("[3DSBANK] note\nFOLDER_SLOT=2\n[OTHER] note\nFOLDER_SLOT=3\n")
        self.scan()
        self.assertEqual(self.meta["active"], 2)
        self.assertEqual(self.meta["warnings"], 0)

    def test_equals_annotated_boundary_is_ambiguous_upstream(self):
        self.healthy()
        self.config("[3DSBANK]\nFOLDER_SLOT=2\n[OTHER]=note\nFOLDER_SLOT=3\n")
        self.scan()
        self.assert_unknown()

    def test_line_endings_and_unterminated_final_alias(self):
        self.directory("Nintendo 3DS")
        for ending in ["\r", "\n", "\r\n"]:
            for final in ["", ending]:
                with self.subTest(ending=repr(ending), final=repr(final)):
                    self.config(ending.join(["\ufeff[3DSBANK]", "FOLDER_SLOT=2", "SLOT_NAME_2=Main"]) + final)
                    self.scan()
                    self.assertEqual(self.meta["warnings"], 0)
                    self.assertEqual(self.rows[2], ["Main", "active (INI)"])

    def test_unterminated_final_active_key(self):
        self.directory("Nintendo 3DS")
        for ending in ["\r", "\n", "\r\n"]:
            self.config("[3DSBANK]" + ending + "FOLDER_SLOT=39")
            self.scan()
            self.assertEqual(self.meta["active"], 39)
            self.assertEqual(self.meta["warnings"], 0)

    def test_maximum_supported_stored_bank_count(self):
        self.config("[3DSBANK]\n")
        for n in range(40):
            self.directory(f"3DSBank/Slot{n}")
        self.scan()
        self.assertEqual(self.meta["stored"], 40)
        self.assert_unknown()
        self.assertTrue(all(row[1] == "stored" for row in self.rows.values()))

    def test_maximum_banks_including_active(self):
        self.healthy()
        for n in range(40):
            if n != 2:
                self.directory(f"3DSBank/Slot{n}")
        self.scan()
        self.assertEqual(self.meta["stored"], 39)
        self.assertEqual(self.meta["warnings"], 0)
        self.assertEqual(self.rows[39][1], "stored")

    def test_oversized_numeric_directory_names_are_not_io_errors(self):
        self.healthy()
        for length in [30, 100, 251]:
            self.directory("3DSBank/Slot" + "9" * length)
        self.scan()
        self.assertEqual(self.meta["warnings"], 32)
        self.assertEqual(self.meta["active"], 2)

    def test_overflow_immediately_before_directory_eof(self):
        self.healthy()
        self.scan(fault="overflow-entry")
        self.assertEqual(self.meta["warnings"], 32)

    def test_alias_buffer_boundaries(self):
        self.directory("Nintendo 3DS")
        for length in [0, 1, 94, 95, 96, 97]:
            with self.subTest(length=length):
                self.config("[3DSBANK]\nFOLDER_SLOT=2\nSLOT_NAME_2=" + "A" * length)
                self.scan()
                self.assertEqual(self.rows[2][0], "A" * min(length, 95))
                self.assertEqual(self.meta["warnings"], 16 if length > 95 else 0)

    def test_line_buffer_boundaries(self):
        self.directory("Nintendo 3DS")
        for length in [510, 511, 512]:
            with self.subTest(length=length):
                self.config("[3DSBANK]\nFOLDER_SLOT=2\n;" + "A" * (length - 1))
                self.scan()
                if length <= 511:
                    self.assertEqual(self.meta["warnings"], 0)
                else:
                    self.assert_unknown()
                    self.assertTrue(self.meta["warnings"] & 16)

    def test_config_read_limit_boundaries(self):
        self.directory("Nintendo 3DS")
        prefix = "[3DSBANK]\nFOLDER_SLOT=2\n"
        for size in [65535, 65536, 65537]:
            with self.subTest(size=size):
                self.config(prefix + "\n" * (size - len(prefix)))
                self.scan()
                if size < 65536:
                    self.assertEqual(self.meta["warnings"], 0)
                else:
                    self.assert_unknown()
                    self.assertTrue(self.meta["warnings"] & 16)

    def test_path_buffer_boundaries(self):
        for size in [491, 492, 493, 600]:
            with self.subTest(size=size):
                # Long existing root path; no individual component exceeds NAME_MAX.
                padding = size - len(str(self.root))
                parts = []
                while padding:
                    count = min(padding - 1, 100)
                    if padding - count - 1 == 1:
                        count -= 1
                    parts.append("x" * count)
                    padding -= count + 1
                root = self.root.joinpath(*parts)
                root.mkdir(parents=True, exist_ok=True)
                self.scan(root)
                self.assertEqual(bool(self.meta["warnings"] & 16), size >= 492)
                if size < 492:
                    self.assert_unknown()
                else:
                    self.assertEqual(self.meta["active"], -1)

    def test_unreadable_config_open(self):
        self.healthy()
        self.scan(fault="fopen")
        self.assert_unknown()
        self.assertTrue(self.meta["warnings"] & 1)
        self.assertEqual(self.meta["config"], 0)

    def test_config_late_read_failure_invalidates_active(self):
        self.healthy()
        self.scan(fault="fgetc")
        self.assert_unknown()
        self.assertTrue(self.meta["warnings"] & 1)

    def test_directory_open_failure(self):
        self.healthy()
        self.scan(fault="opendir")
        self.assertTrue(self.meta["warnings"] & 1)

    def test_directory_read_failure(self):
        self.healthy()
        self.scan(fault="readdir")
        self.assertTrue(self.meta["warnings"] & 1)

    def test_bank_stat_failure(self):
        self.healthy()
        self.scan(fault="stat")
        self.assertTrue(self.meta["warnings"] & 1)
        self.assertEqual(self.rows[7][1], "read error")

    def test_selected_bank_stat_failure_is_conflict(self):
        self.directory("Nintendo 3DS")
        self.config("[3DSBANK]\nFOLDER_SLOT=7\n")
        self.scan(fault="stat")
        self.assertEqual(self.rows[7][1], "CONFLICT")
        self.assertEqual(self.meta["warnings"] & 9, 9)

    def test_repeated_scans_clear_previous_state(self):
        self.healthy()
        self.directory("3DSBank/Slot3")
        self.scan()
        self.assertEqual(self.meta["active"], 2)
        # CLI scans this healthy tree, then repeats the empty tree in the same struct.
        empty = self.root / "empty"
        empty.mkdir()
        result = subprocess.run([str(self.exe), str(self.root), str(empty)], check=True,
                                capture_output=True, text=True).stdout.splitlines()
        meta = dict(item.split("=") for item in result[0].split())
        self.assertEqual(meta["active"], "-1")
        self.assertEqual(meta["stored"], "0")
        self.assertEqual(result[3], "2|Slot 2|absent")



if __name__ == "__main__":
    unittest.main()
