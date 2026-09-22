"""Binary client for the development-only XSI Debug Hub oracle."""

import socket
import struct
import threading


class XsiDebug:
    def __init__(self, path):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.connect(path)
        self.lock = threading.Lock()

    def _receive(self, count):
        result = bytearray()
        while len(result) < count:
            chunk = self.socket.recv(count - len(result))
            if not chunk:
                raise EOFError("XSI oracle disconnected")
            result.extend(chunk)
        return bytes(result)

    def shift_vector(self, count, tms, tdi):
        with self.lock:
            self.socket.sendall(struct.pack("<I", count) + tms + tdi)
            return self._receive((count + 7) // 8)

    def close(self):
        self.socket.close()
