import socket
import struct
import zlib

TYPE_DATA = 0x01    # 普通数据包
TYPE_ACK = 0x02     # 确认包
TYPE_ERROR = 0x03

# 数据包结构：序列号(4字节) + 类型(1字节) + 校验和(4字节) + 数据长度(2字节) + 数据(可变)
HEADER_FORMAT = '!IBI'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

def calculate_checksum(data):
    """计算CRC-32校验和"""
    return zlib.crc32(data) & 0xFFFFFFFF

def create_packet(seq_num, packet_type, payload):
    """构造数据包"""
    payload_length = len(payload)
    header = struct.pack(HEADER_FORMAT, seq_num, packet_type, 0)
    checksum = calculate_checksum(header + payload)
    header = struct.pack(HEADER_FORMAT, seq_num, packet_type, checksum)
    return header + payload

def parse_packet(packet):
    """解析数据包"""
    header = packet[:HEADER_SIZE]
    payload = packet[HEADER_SIZE:]
    seq_num, packet_type, checksum = struct.unpack(HEADER_FORMAT, header)
    calculated_checksum = calculate_checksum(header[:HEADER_SIZE - 4] + payload)
    if checksum != calculated_checksum:
        raise ValueError("校验和错误")
    return seq_num, packet_type, payload

def send_packet(sock, addr, seq_num, packet_type, payload):
    """发送数据包"""
    packet = create_packet(seq_num, packet_type, payload)
    sock.sendto(packet, addr)

def receive_packet(sock):
    """接收数据包"""
    packet, addr = sock.recvfrom(1024)
    try:
        seq_num, packet_type, payload = parse_packet(packet)
        return seq_num, packet_type, payload, addr
    except ValueError as e:
        print(f"接收数据包时出错: {e}")
        return None, None, None, addr