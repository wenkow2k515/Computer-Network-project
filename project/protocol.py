# protocol.py
import socket
import struct
import binascii
from enum import IntEnum

class PacketType(IntEnum):
    DATA = 0       # Data packet
    ACK = 1        # Acknowledgment packet
    NACK = 2       # Negative acknowledgment packet (request retransmission)
    ERROR = 3      # Error packet

class Packet:
    """
    Custom protocol packet structure:
    - Sequence number (4 bytes, unsigned integer)
    - Packet type (1 byte, unsigned integer, corresponding to PacketType)
    - Data length (2 bytes, unsigned integer)
    - Checksum (4 bytes, CRC-32)
    - Data (variable length)
    """
    HEADER_FORMAT = "!IBH4s"  # Network byte order (big-endian)
    HEADER_SIZE = 4 + 1 + 2 + 4  # 11 bytes

    def __init__(self, seq_num: int, ptype: PacketType, data: bytes = b''):
        self.seq_num = seq_num
        self.ptype = ptype
        self.data = data
        self.checksum = self._calculate_checksum()

    def _calculate_checksum(self) -> bytes:
        """Calculate CRC-32 checksum (including header and data)"""
        header_without_checksum = struct.pack(
            "!IBH",
            self.seq_num,
            self.ptype.value,
            len(self.data)
        )
        crc_data = header_without_checksum + self.data
        checksum = binascii.crc32(crc_data).to_bytes(4, byteorder='big')
        return checksum

    def pack(self) -> bytes:
        """Serialize the packet into a byte stream"""
        header = struct.pack(
            self.HEADER_FORMAT,
            self.seq_num,
            self.ptype,
            len(self.data),
            self.checksum
        )
        return header + self.data

    @classmethod
    def unpack(cls, raw_data: bytes):
        """Parse the packet from a byte stream"""
        if len(raw_data) < cls.HEADER_SIZE:
            raise ValueError("Invalid packet length")

        header = raw_data[:cls.HEADER_SIZE]
        data = raw_data[cls.HEADER_SIZE:]

        # Parse the header
        seq_num, ptype, data_len, checksum = struct.unpack(cls.HEADER_FORMAT, header)
        ptype = PacketType(ptype)

        # Validate data length
        if data_len != len(data):
            raise ValueError("Data length mismatch")

        # Create a temporary packet object to validate the checksum
        temp_packet = cls(seq_num, ptype, data)
        temp_packet.checksum = checksum
        if not temp_packet.validate():
            raise ValueError("Checksum mismatch")

        return temp_packet

    def validate(self) -> bool:
        """Validate if the checksum matches"""
        expected_checksum = self._calculate_checksum()
        return self.checksum == expected_checksum


def send_packet(sock: socket.socket, packet: Packet, address: tuple = None):
    """Send a packet (supports UDP or TCP)"""
    data = packet.pack()
    if sock.type == socket.SOCK_DGRAM:  # UDP
        sock.sendto(data, address)
    else:  # TCP
        sock.sendall(data)


def recv_packet(sock: socket.socket) -> Packet:
    """Receive a packet (supports UDP or TCP)"""
    if sock.type == socket.SOCK_DGRAM:
        raw_data, _ = sock.recvfrom(4096)
    else:
        header_data = b''
        while len(header_data) < Packet.HEADER_SIZE:
            chunk = sock.recv(Packet.HEADER_SIZE - len(header_data))
            if not chunk:
                raise ConnectionError("Connection closed")
            header_data += chunk
        _, _, data_len, _ = struct.unpack(Packet.HEADER_FORMAT, header_data)
        data = b''
        while len(data) < data_len:
            chunk = sock.recv(data_len - len(data))
            if not chunk:
                raise ConnectionError("Connection closed")
            data += chunk
        raw_data = header_data + data
    return Packet.unpack(raw_data)

sessions = {} #{conn: ClientSession}