# backend/utils.py

import os
import sys
import struct
import socket
import logging
from typing import List

log = logging.getLogger(__name__)

def is_frozen() -> bool:
    """ 检查程序是否被 PyInstaller 打包 """
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')

def get_project_root() -> str:
    """ 获取项目的根目录 """
    if is_frozen():
        return os.path.dirname(sys.executable)
    else:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def get_local_ip() -> str:
    """ 尝试获取用于与外部通信的本机局域网IP地址 """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0.1)
    try:
        # 不需要实际发送数据
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except (socket.error, OSError):
        try:
            # 备选方案
            ip = socket.gethostbyname(socket.gethostname())
        except socket.gaierror:
            # 最后的备选
            ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def float_to_modbus_registers(float_value: float) -> List[int]:
    """
    将32位浮点数转换为两个16位Modbus寄存器值 (遵循小端模式)
    """
    # 先按大端字节序打包成4字节
    packed_bytes = struct.pack('>f', float_value)
    # 按小端模式，低位字在前，高位字在后
    # packed_bytes[2:4] 是低位字，packed_bytes[0:2] 是高位字
    low_word = struct.unpack('>H', packed_bytes[2:4])[0]
    high_word = struct.unpack('>H', packed_bytes[0:2])[0]
    return [low_word, high_word]

def modbus_registers_to_float(registers: List[int]) -> float:
    """
    将两个16位Modbus寄存器值转换为32位浮点数 (遵循小端模式)
    """
    if len(registers) != 2:
        log.error(f"需要2个寄存器来转为浮点数，但收到了 {len(registers)} 个。")
        return 0.0
    # registers[0] 是低位字, registers[1] 是高位字
    low_word, high_word = registers
    # 按大端字节序重新组合
    packed_bytes = struct.pack('>HH', high_word, low_word)
    return struct.unpack('>f', packed_bytes)[0]

def is_modbus_response_ok(response) -> bool:
    """ 通用检查Modbus响应是否成功 """
    if response is None:
        return False
    # isError() 是 pymodbus 3.x 的方法
    if hasattr(response, 'isError') and callable(response.isError):
        return not response.isError()
    # is_exception() 是旧版本的方法
    if hasattr(response, 'is_exception') and callable(response.is_exception):
        return not response.is_exception()
    # 如果没有错误检查方法，但有寄存器，也认为是成功的
    if hasattr(response, 'registers'):
        return True
    return False