"""Host fixtures only. Never point this test suite at a real SD card."""
import hashlib
import os
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
                        "-Werror", "-I", str(REPO / "include"), str(REPO / "source/banks.c"),
                        str(REPO / "tests/scan_cli.c"), "-o", str(cls.exe)], check=True)

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

    def scan(self, root=None):
        before = self.snapshot()
        result = subprocess.run([str(self.exe), str(root or self.root)],
                                check=True, capture_output=True, text=True).stdout.splitlines()
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


if __name__ == "__main__":
    unittest.main()
