"""Structural validation for this project's no-RomFS 3DSX + SMDH output.

Matches devkitPro/3dstools src/3dsxtool.cpp's header/segment/relocation layout.
This does not execute the application or establish hardware compatibility.
"""
import argparse
from pathlib import Path
import struct

SMDH_SIZE = 0x36C0


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(executable, metadata):
    require(len(metadata) == SMDH_SIZE, "SMDH size must be 0x36c0")
    require(metadata[:4] == b"SMDH", "invalid SMDH magic")
    require(metadata[4:8] == b"\0" * 4, "unsupported SMDH version/reserved fields")
    require(len(executable) >= 68, "truncated 3DSX header/relocation headers")
    fields = struct.unpack_from("<4sHH9I", executable)
    magic, header, reloc_header, version, flags, code, rodata, data, bss, offset, size, romfs = fields
    require(magic == b"3DSX", "invalid 3DSX magic")
    require((header, reloc_header, version, flags, romfs) == (44, 8, 0, 0, 0),
            "unsupported 3DSX header (expected embedded SMDH, no RomFS)")
    require(code > 0 and all(n % 4 == 0 for n in [code, rodata, data, bss]),
            "empty code or unaligned segment sizes")
    require(bss <= data, "BSS exceeds data segment")
    counts = struct.unpack_from("<6I", executable, header)
    reloc_start = header + 3 * reloc_header + code + rodata + data - bss
    require(reloc_start + sum(counts) * 4 == offset, "invalid segment/relocation bounds")
    require(size == len(metadata) and offset + size == len(executable),
            "truncated/trailing 3DSX data or invalid SMDH bounds")
    require(executable[offset:] == metadata, "embedded SMDH differs from published SMDH")
    cursor = reloc_start
    for segment, segment_size in enumerate([code, rodata, data]):
        for count in counts[segment * 2:segment * 2 + 2]:
            word = 0
            for _ in range(count):
                skip, patch = struct.unpack_from("<HH", executable, cursor)
                cursor += 4
                word += skip + patch
                require(word <= segment_size // 4, "relocation exceeds segment bounds")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("metadata", type=Path)
    args = parser.parse_args()
    validate(args.executable.read_bytes(), args.metadata.read_bytes())
    print("3DSX segments/relocations and embedded/external SMDH validated")
