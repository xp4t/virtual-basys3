"""Incremental model of the 7-series Debug Hub BSCAN switch."""


_CORE_MAP_WORD = 0x00000000000500B08008070870080800
CORE_MAP = sum(_CORE_MAP_WORD << (128 * index) for index in range(10)) & ((1 << 1243) - 1)

# Register map returned by the one-probe, depth-1024 ILA in the acceptance
# design.  The native BSCANE2 replay is sparse: six header flags followed by
# one presence flag in each of 128 256-bit probe descriptors.
ILA_REGISTER_WIDTH = 35083
ILA_REGISTER_MAP = (
    sum(1 << bit for bit in (21, 43, 59, 411, 2043, 2075))
    | sum(1 << bit for bit in range(2158, 34671, 256))
)


class DebugHub:
    """Expose the verified XSDB master and ILA metadata discovery handshake.

    Values are derived by replaying Vivado's XVC requests against the
    post-route ILA acceptance design. This deliberately does not claim ILA
    capture support; transactions after core discovery remain an empty FIFO.
    """

    def __init__(self, configured):
        self.configured = configured
        self.next_value = 0x04900101
        self.next_width = 32
        self.last_value = 0
        self.state = "identify"
        self.query_counts = {}
        self.slave_identification = False
        self.slave_transition = False
        self.current_address = None
        self.ila_register_read = False

    def query(self, address):
        if self.slave_identification:
            if address == 0x600 and self.ila_register_read:
                self.ila_register_read = False
                return ILA_REGISTER_MAP, ILA_REGISTER_WIDTH
            stable = {
                0x400: (0x0060008000, 37),
                0x500: (0x07FF0000, 27),
                0x600: (0x0000000003F480808301000080010008800, 139),
            }
            if address in stable:
                return stable[address]
        responses = {
            0x000: (1243, (CORE_MAP,)),
            0x100: (11, (0,)),
            0x200: (15, (0x3800,)),
            0x400: (37, (0, 0x0060008000)),
            # The ILA metadata ports are clock-domain-crossing register
            # streams.  The third samples below are real intermediate values
            # observed when Vivado switches through USER3 and re-enumerates.
            0x500: (27, (0, 0x07FF0000, 0x07F00000, 0x07FF0000)),
            0x600: (139, (0x0000000003F480808301000080010008800,
                           0x621FBB4B686A2FB0C7417CB6CCA6FBF7800,
                           0x0000000003F480808301000080010008800,
                           0x621FBB4B686A2FB0C7417CB6CCA6FBF7800)),
            0xF000: (75, (0x0B08008070808080FFF,)),
        }
        width, values = responses.get(address, (32, (0,)))
        count = self.query_counts.get(address, 0)
        self.query_counts[address] = count + 1
        result = values[min(count, len(values) - 1)], width
        # USER3 starts a CDC hand-off, but the next 0x400/0x500/0x600 tuple
        # is still transitional.  The downstream slave is stable only after
        # that tuple's final 0x600 sample has crossed the boundary.
        if self.slave_transition and address == 0x600:
            self.slave_transition = False
            self.slave_identification = True
        return result

    def capture(self, instruction):
        if not self.configured():
            return 0, 1
        if int(instruction) != 0x02:
            # Selecting another USER chain resets the BSCAN switch framing,
            # but not the downstream ILA register synchronizers.
            self.state = "identify"
            self.next_value = 0x04900101
            self.next_width = 32
            if int(instruction) == 0x22:
                # USER3 separates UUID enumeration from opening the selected
                # XSDB slave.  The latter reads the stable slave descriptor,
                # not the UUID stream's next word.
                self.slave_transition = True
            # An unconnected BSCANE2 USER chain is a zero-filled scan path,
            # not the device's one-bit BYPASS register.  Keep it wider than
            # every discovery vector so shifted TDI cannot reappear on TDO.
            return 0, 8192
        self.last_value = self.next_value
        return self.last_value, self.next_width

    def update(self, instruction, tdi, bit_count):
        if int(instruction) != 0x02 or not self.configured():
            return
        # Verified BSCAN-switch discovery state transitions.
        if bit_count == 32 and tdi == 0x04900100:
            self.next_value = 0x04900220
            self.next_width = 32
        elif bit_count == 32 and tdi == 0 and self.last_value == 0x04900220:
            self.next_value = 0x04900101
            self.next_width = 32
        elif bit_count == 32 and tdi == 0x04900180:
            self.state = "query_status"
            self.next_value, self.next_width = 0, 32
        elif self.state == "query_status" and bit_count == 17:
            self.state = "query_payload"
            self.current_address = tdi
            self.next_value, self.next_width = self.query(tdi)
        elif self.state == "query_payload":
            # 0x60890a9 is the command that opens the selected ILA's full
            # register stream.  Vivado issues it to port 0x400, then reads
            # ports 0x500 and 0x600; the latter changes from the 139-bit
            # slave descriptor to the 35,083-bit register map.
            if (self.slave_identification and self.current_address == 0x400
                    and bit_count == 37 and tdi == 0x00060890A9):
                self.ila_register_read = True
            self.state = "identify"
            self.current_address = None
            self.next_value, self.next_width = 0x04900101, 32
        elif self.state == "identify" and bit_count == 17 and tdi == 0x0F000:
            self.state = "cleanup_short"
            self.next_value, self.next_width = 0, 32
        elif self.state == "cleanup_short" and bit_count == 75:
            self.state = "cleanup_status"
            self.next_value, self.next_width = 0, 32
        elif self.state == "cleanup_status" and bit_count == 17 and tdi == 0:
            self.state = "cleanup_payload"
            self.next_value, self.next_width = 0, 32
        elif self.state == "cleanup_payload" and bit_count == 1243:
            self.state = "identify"
            self.next_value, self.next_width = 0x04900101, 32
