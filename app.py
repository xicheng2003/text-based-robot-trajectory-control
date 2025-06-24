from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS # 用于处理跨域请求
from pymodbus.client import ModbusTcpClient 
from pymodbus.exceptions import ModbusException
import struct
import time
import logging

# 配置日志，设置为INFO级别，便于查看关键操作，DEBUG级别用于更详细的Modbus通信日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app) # 允许跨域请求，前端才能访问后端API

# --- 机器人Modbus连接配置 ---
ROBOT_IP = '192.168.0.11' # <-- 请根据你的机器人实际IP地址修改！
ROBOT_PORT = 502          # 培高系统Modbus TCP默认端口
SLAVE_ID = 1              # Modbus从站ID，博创系统默认从站地址为1

# Modbus客户端实例，全局维护
modbus_client = None

# --- 辅助函数：浮点数与Modbus寄存器值转换 ---
def float_to_modbus_registers(float_value):
    """
    将32位浮点数转换为两个16位Modbus寄存器值 (遵循博创系统的小端模式)
    """
    ieee_754_bytes = struct.pack('>f', float_value) 
    high_word_bytes = ieee_754_bytes[0:2]  
    low_word_bytes = ieee_754_bytes[2:4]   
    register_low = int.from_bytes(low_word_bytes, byteorder='big')
    register_high = int.from_bytes(high_word_bytes, byteorder='big')
    return [register_low, register_high] 

def modbus_registers_to_float(registers):
    """
    将两个16位Modbus寄存器值转换为32位浮点数 (遵循博创系统的小端模式)
    """
    if len(registers) != 2:
        return 0.0 # 错误处理，返回0.0
    register_low = registers[0]
    register_high = registers[1]
    low_word_bytes = register_low.to_bytes(2, byteorder='big')
    high_word_bytes = register_high.to_bytes(2, byteorder='big')
    ieee_754_bytes = high_word_bytes + low_word_bytes
    float_value = struct.unpack('>f', ieee_754_bytes)[0]
    return float_value

# --- 通用检查Modbus响应是否成功的方法 (与之前的Demo和排查脚本一致) ---
def is_modbus_response_ok(response):
    """
    通用检查Modbus响应是否成功的方法。
    """
    if response is None:
        return False
    if hasattr(response, 'isOk') and callable(response.isOk):
        return response.isOk()
    if hasattr(response, 'isError') and callable(response.isError):
        return not response.isError()
    if hasattr(response, 'is_exception') and callable(response.is_exception):
        return not response.is_exception()
    if hasattr(response, 'registers') and response.registers is not None:
        return True 
    return True 

# --- Modbus操作通用封装 (与之前的Demo和排查脚本一致) ---
# 这些函数依赖于 modbus_client.unit 已经被设置
def _execute_modbus_read(client, address, count, operation_name):
    """通用Modbus读取函数"""
    log.debug(f"正在执行: {operation_name} (地址: {address}, 数量: {count})")
    try:
        result = client.read_holding_registers(address=address, count=count)
        if is_modbus_response_ok(result):
            log.debug(f"{operation_name} 成功. 值: {result.registers}")
            return result.registers
        else:
            log.error(f"{operation_name} 失败. Modbus响应: {result}")
            return None
    except ModbusException as e:
        log.error(f"{operation_name} Modbus异常: {e}")
        return None
    except Exception as e:
        log.error(f"{operation_name} 过程中发生未知错误: {e}")
        return None

def _execute_modbus_write_single(client, address, value, operation_name):
    """通用Modbus写单个寄存器函数"""
    log.debug(f"正在执行: {operation_name} (地址: {address}, 值: {value})")
    try:
        result = client.write_register(address=address, value=value)
        if is_modbus_response_ok(result):
            log.debug(f"{operation_name} 成功.")
            return True
        else:
            log.error(f"{operation_name} 失败. Modbus响应: {result}")
            return False
    except ModbusException as e:
        log.error(f"{operation_name} Modbus异常: {e}")
        return False
    except Exception as e:
        log.error(f"{operation_name} 过程中发生未知错误: {e}")
        return False

def _execute_modbus_write_multiple(client, address, values, operation_name):
    """通用Modbus写多个寄存器函数"""
    log.debug(f"正在执行: {operation_name} (地址: {address}, 值: {values})")
    try:
        result = client.write_registers(address=address, values=values)
        if is_modbus_response_ok(result):
            log.debug(f"{operation_name} 成功.")
            return True
        else:
            log.error(f"{operation_name} 失败. Modbus响应: {result}")
            return False
    except ModbusException as e:
        log.error(f"{operation_name} Modbus异常: {e}")
        return False
    except Exception as e:
        log.error(f"{operation_name} 过程中发生未知错误: {e}")
        return False

# --- 机器人Modbus控制封装 (从robot_modbus_demo.py中复用和简化) ---
def connect_modbus_client():
    """连接到机器人Modbus TCP从站，并设置全局客户端"""
    global modbus_client
    if modbus_client and modbus_client.connected:
        log.info("Modbus客户端已连接，无需重新连接。")
        return True
    
    log.info(f"尝试连接到机器人 Modbus TCP 从站 {ROBOT_IP}:{ROBOT_PORT}...")
    try:
        client = ModbusTcpClient(host=ROBOT_IP, port=ROBOT_PORT)
        if client.connect():
            client.unit = SLAVE_ID 
            modbus_client = client
            log.info(f"成功连接到机器人，并设置客户端默认 Unit ID 为 {SLAVE_ID}。")
            return True
        else:
            log.error("Modbus连接失败。请检查IP地址、端口和网络设置。")
            modbus_client = None
            return False
    except ModbusException as e:
        log.error(f"Modbus连接异常: {e}")
        modbus_client = None
        return False
    except Exception as e:
        log.error(f"连接过程中发生未知错误: {e}")
        modbus_client = None
        return False

def set_robot_auto_mode_modbus():
    """切换机器人到自动模式 (GV222_L = 1)"""
    if not connect_modbus_client(): return False
    modbus_address = 444 
    value = 1             
    return _execute_modbus_write_single(modbus_client, modbus_address, value, "切换机器人到自动模式")

def set_joint_increment_offset_modbus(angle):
    """设置关节1增量运动偏移量 (GV200 = angle)"""
    if not connect_modbus_client(): return False
    modbus_address_gv200_low = 400 
    registers_to_write = float_to_modbus_registers(float(angle))
    return _execute_modbus_write_multiple(modbus_client, modbus_address_gv200_low, registers_to_write, "设置关节1增量运动偏移量")

def set_move_speed_modbus(speed): 
    """设置期望运动速度 (GV225 = speed)"""
    if not connect_modbus_client(): return False
    modbus_address_gv225_low = 450 
    registers_to_write = float_to_modbus_registers(float(speed))
    return _execute_modbus_write_multiple(modbus_client, modbus_address_gv225_low, registers_to_write, "设置期望运动速度")

def start_increment_move_modbus(): 
    """启动增量运动 (关节坐标系) (GV220_L = 0x40)"""
    if not connect_modbus_client(): return False
    modbus_address = 440  
    value = 0x40          
    return _execute_modbus_write_single(modbus_client, modbus_address, value, "启动增量运动")

def get_robot_status_modbus():
    """读取机器人当前状态：模式，运行状态，报警状态"""
    if not connect_modbus_client(): return None
    
    status_data = {
        "mode": "未知",
        "run_status": "未知",
        "alarm_status": "未知",
        "gv0_value": None # 用于测试写入GV0后的回读
    }

    # 读取控制器模式 (GV280_L, Modbus地址 560)
    mode_registers = _execute_modbus_read(modbus_client, 560, 1, "读取控制器模式 (GV280_L)")
    if mode_registers:
        controller_mode = mode_registers[0]
        mode_map = {0: "手动模式", 1: "自动模式", 2: "Modbus示教使能"}
        status_data["mode"] = mode_map.get(controller_mode, f"未知 ({controller_mode})")

    # 读取程序当前运行状态 (GV280_H, Modbus地址 561)
    run_status_registers = _execute_modbus_read(modbus_client, 561, 1, "读取程序运行状态 (GV280_H)")
    if run_status_registers:
        program_status = run_status_registers[0]
        status_map = {0: "停止", 1: "正在运行", 2: "暂停"}
        status_data["run_status"] = status_map.get(program_status, f"未知 ({program_status})")

    # 读取报警类型 (GV281_L, Modbus地址 562)
    alarm_registers = _execute_modbus_read(modbus_client, 562, 1, "读取报警类型 (GV281_L)")
    if alarm_registers:
        alarm_code = alarm_registers[0]
        if alarm_code == 0:
            status_data["alarm_status"] = "无报警"
        else:
            alarm_desc = []
            if (alarm_code & 0b00000001) != 0: alarm_desc.append("急停报警")
            if (alarm_code & 0b00000010) != 0: alarm_desc.append("伺服报警")
            if (alarm_code & 0b00000100) != 0: alarm_desc.append("刹车异常报警")
            if (alarm_code & 0b00001000) != 0: alarm_desc.append("算法报警")
            if (alarm_code & 0b00010000) != 0: alarm_desc.append("获取编码器角度报警")
            status_data["alarm_status"] = f"有报警 ({hex(alarm_code)}): " + ", ".join(alarm_desc) if alarm_desc else f"有报警 ({hex(alarm_code)})"

    # 读取GV0测试值 (Modbus地址 0)
    gv0_registers = _execute_modbus_read(modbus_client, 0, 2, "读取GV0测试值")
    if gv0_registers:
        status_data["gv0_value"] = modbus_registers_to_float(gv0_registers)

    return status_data

def write_gv0_test_value_modbus(value):
    """向GV0写入一个测试值 (浮点数)"""
    if not connect_modbus_client(): return False
    modbus_address_gv0_low = 0
    registers_to_write = float_to_modbus_registers(float(value))
    return _execute_modbus_write_multiple(modbus_client, modbus_address_gv0_low, registers_to_write, f"写入测试值 {value} 到 GV0")

# --- Flask 路由和API ---

@app.route('/')
def serve_index():
    """提供index.html文件"""
    return send_from_directory('.', 'index.html')

@app.route('/command', methods=['POST'])
def handle_command():
    data = request.get_json()
    command_text = data.get('command', '').strip().upper()
    log.info(f"收到指令: {command_text}")

    response_message = "指令已接收，正在处理。"
    status = "processing"
    robot_status_info = {}

    try:
        # 连接到机器人Modbus客户端
        if not connect_modbus_client():
            raise Exception("无法连接到机器人Modbus。")

        # --- 基础命令解析 ---
        if command_text == "AUTO_MODE":
            success = set_robot_auto_mode_modbus()
            if success:
                response_message = "机器人已尝试切换到自动模式。"
                status = "success"
            else:
                response_message = "切换自动模式失败。"
                status = "error"
        
        elif command_text.startswith("MOVE J"):
            parts = command_text.split()
            if len(parts) == 3 and parts[0] == "MOVE" and parts[1].startswith("J"):
                try:
                    axis_id_str = parts[1][1:]
                    axis_id = int(axis_id_str) # 暂未使用，此demo只控制J1
                    angle = float(parts[2])
                    if axis_id == 1: # 仅支持关节1的增量运动
                        success = set_joint_increment_offset_modbus(angle)
                        if success:
                            response_message = f"已设置关节J{axis_id}增量运动 {angle} 度。"
                            status = "success"
                        else:
                            response_message = f"设置关节J{axis_id}增量运动失败。"
                            status = "error"
                    else:
                        response_message = "当前DEMO仅支持J1轴的MOVE指令。"
                        status = "error"
                except ValueError:
                    response_message = "MOVE指令参数格式错误，请检查角度是否为数字。"
                    status = "error"
            else:
                response_message = "MOVE指令格式错误，应为 'MOVE J<轴号> <角度>'。"
                status = "error"

        elif command_text.startswith("SET_SPEED"):
            parts = command_text.split()
            if len(parts) == 2:
                try:
                    speed = float(parts[1])
                    success = set_move_speed_modbus(speed)
                    if success:
                        response_message = f"已设置运动速度为 {speed}。"
                        status = "success"
                    else:
                        response_message = "设置运动速度失败。"
                        status = "error"
                except ValueError:
                    response_message = "SET_SPEED指令参数格式错误，速度值应为数字。"
                    status = "error"
            else:
                response_message = "SET_SPEED指令格式错误，应为 'SET_SPEED <速度值>'。"
                status = "error"
        
        elif command_text == "START_MOVE":
            success = start_increment_move_modbus()
            if success:
                response_message = "机器人已尝试启动增量运动。"
                status = "success"
            else:
                response_message = "启动增量运动失败。"
                status = "error"
        
        elif command_text == "MONITOR":
            robot_status_info = get_robot_status_modbus()
            if robot_status_info:
                response_message = "已获取机器人当前状态。"
                status = "success"
            else:
                response_message = "获取机器人状态失败。"
                status = "error"

        elif command_text.startswith("TEST_WRITE_GV0"):
            parts = command_text.split()
            if len(parts) == 2:
                try:
                    value = float(parts[1])
                    success = write_gv0_test_value_modbus(value)
                    if success:
                        response_message = f"已向GV0写入测试值 {value}。"
                        status = "success"
                    else:
                        response_message = "向GV0写入测试值失败。"
                        status = "error"
                except ValueError:
                    response_message = "TEST_WRITE_GV0指令参数格式错误，值应为数字。"
                    status = "error"
            else:
                response_message = "TEST_WRITE_GV0指令格式错误，应为 'TEST_WRITE_GV0 <值>'。"
                status = "error"
        
        else:
            response_message = "未知指令或指令格式错误。"
            status = "error"

    except Exception as e:
        log.error(f"处理指令 '{command_text}' 时发生异常: {e}")
        response_message = f"服务器内部错误: {e}"
        status = "error"
    
    # 每次指令处理后尝试更新机器人最新状态
    if status != "error": # 如果前面没有发生 Modbus 异常，则尝试获取最新状态
         current_robot_status = get_robot_status_modbus()
         if current_robot_status:
             robot_status_info = current_robot_status
         else:
             log.warning("处理指令后未能获取到机器人最新状态。")


    return jsonify({"status": status, "message": response_message, "robot_status": robot_status_info})

# Flask 应用启动时运行的函数
if __name__ == '__main__':
    # Flask默认会在127.0.0.1:5000上运行
    # debug=True 会在代码更改时自动重启服务器，并提供调试信息
    app.run(debug=True, host='0.0.0.0', port=5000) # host='0.0.0.0'允许从任何IP访问
