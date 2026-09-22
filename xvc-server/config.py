"""7-series configuration transport/status, not a fabric decoder.

Phase 2 accepts unencrypted configuration words and models successful CRC handling.
It does not claim to verify frame CRC or simulate programmed logic.
"""

import logging
from collections import deque
from pathlib import Path

LOG = logging.getLogger("config")
SYNC = 0xAA995566
DEVICE_ID = 0x0362D093


def reverse32(value):
    return int(f"{value:032b}"[::-1], 2)


class Configuration:
    def __init__(self, capture_path=None, on_programmed=None, on_reset=None):
        self.capture_path = Path(capture_path) if capture_path else None
        self.on_programmed = on_programmed
        self.on_reset = on_reset
        self.reset()

    def reset(self):
        self.done = False
        self.init_complete = True
        self.isc_enabled = False
        self.isc_done = False
        self.id_error = False
        self.have_id = False
        self.fdri_words = 0
        self.start_requested = False
        self.start_clocks = 0
        self.registers = {}
        self.synced = False
        self.word = self.word_bits = 0
        self.address = self.opcode = self.remaining = 0
        self.output = deque()
        self.accepted = bytearray()
        self.collecting = False

    @property
    def ir_capture(self):
        return (1 | (self.isc_done << 2) | (self.isc_enabled << 3) |
                (self.init_complete << 4) | (self.done << 5))

    @property
    def status(self):
        # UG470 Tables 5-28/29: JTAG mode 101, INIT_B, INIT_COMPLETE,
        # unused DCI/MMCM report matched/locked. Startup phase 7 encodes 100.
        value = (5 << 8) | (self.init_complete << 11) | (self.init_complete << 12) | 0x0C
        if self.done:
            value |= (4 << 18) | (1 << 14) | (1 << 13) | 0xF0
        return value | (self.id_error << 15)

    def instruction(self, instruction):
        if instruction == 0x0B:  # JPROGRAM
            self.reset()
            if self.on_reset:
                self.on_reset()
            self.collecting = True
            LOG.info("JPROGRAM: configuration cleared")
        elif instruction == 0x10:
            self.isc_enabled = True
        elif instruction == 0x16:
            self.isc_enabled = False
        elif instruction == 0x0C:
            self.start_requested = True
        elif instruction == 0x0D:
            self.done = False

    def idle_clock(self):
        if self.start_requested and not self.done and self.fdri_words and not self.id_error:
            self.start_clocks += 1
            if self.start_clocks >= 64:
                self.done = self.isc_done = True
                self.collecting = False
                if self.capture_path:
                    self.capture_path.parent.mkdir(parents=True, exist_ok=True)
                    self.capture_path.write_bytes(self.accepted)
                LOG.info("Startup complete: DONE=1 FDRI words=%d captured=%d bytes",
                         self.fdri_words, len(self.accepted))
                if self.on_programmed:
                    self.on_programmed(self.accepted)

    def feed_bit(self, bit):
        self.word = ((self.word << 1) | bit) & 0xFFFFFFFF
        self.word_bits += 1
        if not self.synced:
            # Synchronization can be preceded by arbitrary dummy/alignment bits.
            if self.word == SYNC and self.word_bits >= 32:
                self.synced = True
                self.word_bits = 0
                if self.collecting:
                    self.accepted.extend(SYNC.to_bytes(4, "big"))
        elif self.word_bits == 32:
            self.word_bits = 0
            self.feed_word(self.word)

    def feed_word(self, word):
        if self.collecting:
            if len(self.accepted) >= 32 * 1024 * 1024:
                raise ValueError("configuration exceeds 32 MiB capture limit")
            self.accepted.extend(word.to_bytes(4, "big"))
        if self.remaining:
            self.write_register(self.address, word)
            self.remaining -= 1
            return
        if word == SYNC or word == 0xFFFFFFFF:
            return
        kind = word >> 29
        if kind == 1:
            self.opcode = (word >> 27) & 3
            self.address = (word >> 13) & 0x3FFF
            count = word & 0x7FF
        elif kind == 2:
            self.opcode = (word >> 27) & 3
            count = word & 0x7FFFFFF
        else:
            LOG.debug("Ignoring non-packet word 0x%08x", word)
            return
        if self.opcode == 2:
            self.remaining = count
        elif self.opcode == 1:
            if count > 1024:
                raise ValueError("Phase 2 supports register readback, not bulk frame readback")
            self.output.extend(self.read_register(self.address) for _ in range(count))
            LOG.debug("Read register %02x count=%d value=%08x", self.address, count,
                      self.read_register(self.address))

    def write_register(self, address, word):
        if address == 2:  # FDRI: intentionally opaque until Phase 3.
            if not self.have_id:
                self.id_error = True
            self.fdri_words += 1
            return
        self.registers[address] = word
        LOG.debug("Write register %02x=%08x", address, word)
        if address == 12:
            self.have_id = (word & 0x0FFFFFFF) == DEVICE_ID
            self.id_error = not self.have_id
        elif address == 4:  # CMD
            command = word & 0x1F
            if command == 13:  # DESYNC
                self.synced = False
                self.word_bits = self.word = 0
            elif command == 5:  # START, clocked subsequently through JSTART
                self.start_requested = True

    def read_register(self, address):
        if address == 7:
            return self.status
        if address == 12:
            return DEVICE_ID
        return self.registers.get(address, 0)

    def readback_word(self):
        return reverse32(self.output.popleft()) if self.output else 0
