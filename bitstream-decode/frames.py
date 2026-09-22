"""Decode unencrypted, uncompressed 7-series FDRI writes into addressed frames.

Uses prjxray part.json for legal FARs and auto-increment order. Frame row padding
follows prjxray/lib/include/prjxray/xilinx/configuration.h (ISC licensed upstream).
This module is an independent Python implementation, not a bitread subprocess.
"""

import json
import struct
from pathlib import Path

SYNC = bytes.fromhex("aa995566")
WORDS_PER_FRAME = 101
BLOCK_TYPES = {"CLB_IO_CLK": 0, "BLOCK_RAM": 1, "CFG_CLB": 2}


def frame_addresses(part):
    addresses = []
    for half, half_data in part["global_clock_regions"].items():
        for row, row_data in half_data["rows"].items():
            for bus, bus_data in row_data["configuration_buses"].items():
                for col, col_data in bus_data["configuration_columns"].items():
                    base = ((BLOCK_TYPES[bus] << 23) | ((half == "bottom") << 22) |
                            (int(row) << 17) | (int(col) << 7))
                    addresses.extend(base + minor for minor in range(col_data["frame_count"]))
    return sorted(addresses)


def packets(data):
    start = data.find(SYNC)
    if start < 0:
        raise ValueError("Missing 7-series synchronization word")
    payload = data[start + 4:]
    if len(payload) % 4:
        raise ValueError("Configuration payload is not word-aligned")
    words = [word for (word,) in struct.iter_unpack(">I", payload)]
    index = 0
    address = None
    while index < len(words):
        header = words[index]
        index += 1
        if header in (0xFFFFFFFF, 0xAA995566):
            continue
        kind, opcode = header >> 29, (header >> 27) & 3
        if kind == 1:
            address = (header >> 13) & 0x3FFF
            count = header & 0x7FF
        elif kind == 2 and address is not None:
            count = header & 0x7FFFFFF
        else:
            raise ValueError(f"Unsupported packet 0x{header:08x} at word {index}")
        if opcode == 0:
            continue
        if opcode == 1:  # Read commands contain no outgoing payload.
            yield opcode, address, []
            continue
        if opcode != 2 or index + count > len(words):
            raise ValueError("Truncated or invalid configuration packet")
        yield opcode, address, words[index:index + count]
        index += count


def decode_frames(data, part):
    addresses = frame_addresses(part)
    indices = {address: index for index, address in enumerate(addresses)}
    frames = {}
    far = command = mask = ctl1 = 0
    current = None
    start_write = False
    have_id = False
    padding_frames = 0
    for opcode, register, words in packets(data):
        if opcode != 2 or not words:
            continue
        if register == 12:
            expected = part.get("idcode", 0x0362D093)
            if isinstance(expected, str):
                expected = int(expected, 0)
            if (words[0] & 0x0FFFFFFF) != (expected & 0x0FFFFFFF):
                raise ValueError(f"Wrong bitstream device ID: {words[0]:08x}")
            have_id = True
        elif register == 6:
            mask = words[0]
        elif register == 5 and words[0] & 0x40:
            raise ValueError("Encrypted bitstreams are unsupported")
        elif register == 24:
            ctl1 = words[0] & mask
        elif register == 4:
            command = words[0]
            if command == 1:
                start_write = True
            if command == 2:
                raise ValueError("Compressed/MFWR configuration is unsupported")
        elif register == 1:
            far = words[0]
            if command == 1 and not (ctl1 & (1 << 21)):
                start_write = True
        elif register == 2:
            if not have_id:
                raise ValueError("FDRI precedes device ID check")
            if len(words) % WORDS_PER_FRAME:
                raise ValueError("FDRI payload does not contain whole frames")
            if start_write:
                if far not in indices:
                    raise ValueError(f"Unknown FAR: {far:08x}")
                current = indices[far]
                start_write = False
            if current is None:
                raise ValueError("FDRI write without WCFG/FAR")
            position = 0
            while position < len(words):
                if current >= len(addresses):
                    raise ValueError("FDRI writes beyond last legal frame")
                address = addresses[current]
                frames[address] = tuple(words[position:position + WORDS_PER_FRAME])
                position += WORDS_PER_FRAME
                current += 1
                boundary = (current == len(addresses) or
                            (address >> 17) != (addresses[current] >> 17))
                if boundary:
                    padding = words[position:position + 2 * WORDS_PER_FRAME]
                    if len(padding) != 2 * WORDS_PER_FRAME or any(padding):
                        raise ValueError("Missing/nonzero two-frame row padding")
                    position += 2 * WORDS_PER_FRAME
                    padding_frames += 2
    if not frames:
        raise ValueError("No configuration frames decoded")
    return frames, {"frames": len(frames), "padding_frames": padding_frames,
                    "legal_frames": len(addresses), "complete": len(frames) == len(addresses)}


def to_bitdata(frames):
    """prjxray's bitdata representation, excluding frame ECC bits [1612:1600]."""
    result = {}
    for address, words in frames.items():
        columns, bits = set(), set()
        for index, word in enumerate(words):
            if index == 50:
                word &= ~0x1FFF
            if word:
                columns.add(index)
            while word:
                lowest = word & -word
                bits.add(index * 32 + lowest.bit_length() - 1)
                word ^= lowest
        if bits:
            result[address] = (columns, bits)
    return result


def load_part(db_root, part):
    return json.loads((Path(db_root) / part / "part.json").read_text())
