"""Single xc7a35t TAP; one clock() is one complete low/high/low TCK cycle.

See references/README.md for the BSDL and UG470 sources of device constants.
TDO is sampled before the rising edge, capture/shift happen at that edge,
and update latches are committed on the falling edge entering UPDATE.
"""

import logging
from enum import IntEnum

LOG = logging.getLogger("tap")
IDCODE = 0x0362D093
IR_LENGTH = 6


class State(IntEnum):
    RESET = 0
    IDLE = 1
    SELECT_DR = 2
    CAPTURE_DR = 3
    SHIFT_DR = 4
    EXIT1_DR = 5
    PAUSE_DR = 6
    EXIT2_DR = 7
    UPDATE_DR = 8
    SELECT_IR = 9
    CAPTURE_IR = 10
    SHIFT_IR = 11
    EXIT1_IR = 12
    PAUSE_IR = 13
    EXIT2_IR = 14
    UPDATE_IR = 15


# Index by current state, then TMS.
NEXT = (
    (State.IDLE, State.RESET),
    (State.IDLE, State.SELECT_DR),
    (State.CAPTURE_DR, State.SELECT_IR),
    (State.SHIFT_DR, State.EXIT1_DR),
    (State.SHIFT_DR, State.EXIT1_DR),
    (State.PAUSE_DR, State.UPDATE_DR),
    (State.PAUSE_DR, State.EXIT2_DR),
    (State.SHIFT_DR, State.UPDATE_DR),
    (State.IDLE, State.SELECT_DR),
    (State.CAPTURE_IR, State.RESET),
    (State.SHIFT_IR, State.EXIT1_IR),
    (State.SHIFT_IR, State.EXIT1_IR),
    (State.PAUSE_IR, State.UPDATE_IR),
    (State.PAUSE_IR, State.EXIT2_IR),
    (State.SHIFT_IR, State.UPDATE_IR),
    (State.IDLE, State.SELECT_DR),
)


class Instruction(IntEnum):
    SAMPLE = 0x01
    USER1 = 0x02
    USER2 = 0x03
    CFG_OUT = 0x04
    CFG_IN = 0x05
    USERCODE = 0x08
    IDCODE = 0x09
    HIGHZ = 0x0A
    JPROGRAM = 0x0B
    JSTART = 0x0C
    JSHUTDOWN = 0x0D
    ISC_ENABLE = 0x10
    ISC_PROGRAM = 0x11
    ISC_NOOP = 0x14
    ISC_DISABLE = 0x16
    XSC_DNA = 0x17
    USER3 = 0x22
    USER4 = 0x23
    EXTEST = 0x26
    BYPASS = 0x3F


class Tap:
    def __init__(self, config=None, debug=None, raw_debug=None):
        self.config = config
        self.debug = debug
        self.raw_debug = raw_debug
        self.raw_debug_active = False
        self.state = State.RESET
        self.instruction = Instruction.IDCODE
        self.ir = 0
        self.dr = 0
        self.dr_width = 1
        self.dr_count = 0
        self.dr_preview = 0
        self.cycles = 0

    def capture_ir(self):
        if self.config is not None:
            return self.config.ir_capture
        # Unconfigured, initialization complete; BSDL INSTRUCTION_CAPTURE.
        return 0x11

    def capture_dr(self):
        if self.instruction == Instruction.IDCODE:
            self.dr, self.dr_width = IDCODE, 32
        elif self.instruction == Instruction.USERCODE:
            self.dr, self.dr_width = 0xFFFFFFFF, 32
        elif self.instruction == Instruction.CFG_OUT and self.config is not None:
            self.dr, self.dr_width = self.config.readback_word(), 32
        elif self.debug is not None and self.instruction in (
                Instruction.USER1, Instruction.USER2, Instruction.USER3, Instruction.USER4):
            self.dr, self.dr_width = self.debug.capture(self.instruction)
        else:
            # Unsupported instructions use a deterministic one-bit bypass.
            self.dr, self.dr_width = 0, 1
        self.dr_count = self.dr_preview = 0

    def update_ir(self):
        self.instruction = self.ir
        if self.config is not None:
            self.config.instruction(self.instruction)
        LOG.debug("IR=0x%02x cycles=%d", self.instruction, self.cycles)

    def update_dr(self):
        if self.debug is not None and self.instruction in (
                Instruction.USER1, Instruction.USER2, Instruction.USER3, Instruction.USER4):
            self.debug.update(self.instruction, self.dr_preview, self.dr_count)
        LOG.debug("DR instruction=0x%02x bits=%d tdi_first128=0x%x",
                  self.instruction, self.dr_count, self.dr_preview)

    def clock(self, tms, tdi):
        tdo = 0
        state = self.state
        if state == State.IDLE and self.config is not None:
            self.config.idle_clock()
        if state == State.CAPTURE_IR:
            self.ir = self.capture_ir()
        elif state == State.SHIFT_IR:
            tdo = self.ir & 1
            self.ir = (self.ir >> 1) | (tdi << (IR_LENGTH - 1))
        elif state == State.CAPTURE_DR:
            self.capture_dr()
        elif state == State.SHIFT_DR:
            tdo = self.dr & 1
            self.dr = (self.dr >> 1) | (tdi << (self.dr_width - 1))
            if self.dr_count < 128:
                self.dr_preview |= tdi << self.dr_count
            self.dr_count += 1
            if self.config is not None:
                if self.instruction in (Instruction.CFG_IN, Instruction.ISC_PROGRAM):
                    self.config.feed_bit(tdi)
                elif self.instruction == Instruction.CFG_OUT and self.dr_count % 32 == 0:
                    self.dr = self.config.readback_word()

        self.cycles += 1
        self.state = NEXT[state][tms]
        if self.state == State.RESET:
            self.instruction = Instruction.IDCODE
        elif self.state == State.UPDATE_IR:
            self.update_ir()
        elif self.state == State.UPDATE_DR:
            self.update_dr()
        return tdo

    def shift(self, count, tms, tdi):
        size = (count + 7) // 8
        if count < 0 or len(tms) != size or len(tdi) != size:
            raise ValueError("vector lengths must equal ceil(count/8)")
        tdo = bytearray(size)
        raw_mask = bytearray(size)
        initial_state = self.state
        configured = (self.config is not None and self.config.done)
        if not configured:
            self.raw_debug_active = False
        raw_candidate = self.raw_debug is not None and configured
        selected_user = False
        for i in range(count):
            byte, bit = divmod(i, 8)
            use_raw = (raw_candidate
                       and self.state == State.SHIFT_DR
                       and self.instruction in (Instruction.USER1, Instruction.USER2,
                                                Instruction.USER3, Instruction.USER4))
            if use_raw:
                raw_mask[byte] |= 1 << bit
            previous_instruction = self.instruction
            local_tdo = self.clock((tms[byte] >> bit) & 1,
                                   (tdi[byte] >> bit) & 1)
            if (previous_instruction != self.instruction
                    and self.instruction in (Instruction.USER1, Instruction.USER2,
                                             Instruction.USER3, Instruction.USER4)):
                selected_user = True
            tdo[byte] |= local_tdo << bit

        # Configuration vectors can contain millions of bits and the local
        # configuration model already handles them. Once attached, preserve
        # every control transition and USER scan, including fragmented scans.
        # The RTL TAP is initialized in Run-Test/Idle.  Delay attaching it
        # until Vivado actually selects a USER instruction; configuration
        # status traffic before that point is both irrelevant and can leave
        # the two TAPs on different instructions when large scans are elided.
        if raw_candidate and (self.raw_debug_active or selected_user):
            self.raw_debug_active = True
        if (raw_candidate and self.raw_debug_active
                and initial_state == State.IDLE and not any(tms) and count > 64):
            # Vivado emits long idle delays even when its XVC vectors are
            # small. Advance the fabric a little for pending CDC/capture work
            # without simulating every idle TCK. This leaves both TAPs in IDLE.
            self.raw_debug.shift_vector(64, bytes(8), bytes(8))
        elif (raw_candidate and self.raw_debug_active
                and (count <= 8192 or any(raw_mask) or any(tms))):
            raw_tdo = self.raw_debug.shift_vector(count, tms, tdi)
            for byte in range(size):
                tdo[byte] = ((tdo[byte] & ~raw_mask[byte]) |
                             (raw_tdo[byte] & raw_mask[byte]))
        return bytes(tdo)
