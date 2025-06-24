import json
import os
import sys
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS 
from pymodbus.client import ModbusTcpClient 
from pymodbus.exceptions import ModbusException
import struct
import time
import logging
import re # 导入正则表达式模块

# 配置日志，设置为INFO级别，便于查看关键操作，DEBUG级别用于更详细的Modbus通信日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app) # 允许跨域请求，前端才能访问后端API

modbus_client = None

# --- 加载外部配置文件 ---
def load_config():
    config_path = 'config.json'
    if not os.path.exists(config_path):
        # 如果配置文件不存在，可以抛出错误或创建一个默认的
        error_message = f"错误：配置文件 '{config_path}' 未找到。请确保该文件与主程序在同一目录下。"
        print(error_message)
        # 在实际应用中，你可能希望记录日志并退出
        raise FileNotFoundError(error_message)
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # 验证关键配置是否存在
    if 'robot' not in config or 'ip' not in config['robot']:
        raise ValueError("配置文件中缺少 'robot.ip' 配置项。")
        
    return config

# 在程序启动时加载配置
try:
    CONFIG = load_config()
except (FileNotFoundError, ValueError) as e:
    # 优雅地处理配置错误
    log.critical(f"启动失败：{e}")
    sys.exit(1) # 导入sys模块后使用

# --- 从配置中读取参数 ---
ROBOT_IP = CONFIG['robot']['ip']
ROBOT_PORT = CONFIG['robot']['port']
SLAVE_ID = CONFIG['robot']['slave_id']
DEFAULT_SPEED = CONFIG['motion']['default_speed']
SERVER_HOST = CONFIG['server']['host']
SERVER_PORT = CONFIG['server']['port']

current_speed_setting = DEFAULT_SPEED # 上次设置的速度，初始为默认值

# --- 中文指令映射和标准化函数 ---
def normalize_command(command_text):
    """
    尝试将中文指令或其组合规范化为标准的英文指令格式。
    此函数现在通过匹配完整的命令模式（包括中文和英文别名）来工作，
    而不是依赖于简单的startswith和COMMAND_MAPPING字典的迭代顺序。
    """
    command_text_upper = command_text.strip().upper()

    # --- 1. 精确匹配的无参数命令 (英文 & 中文) ---
    if command_text_upper in ["AUTO_MODE", "自动模式"]:
        return "AUTO_MODE"
    if command_text_upper in ["PAUSE_MOVE", "暂停运动"]:
        return "PAUSE_MOVE"
    if command_text_upper in ["CONTINUE_MOVE", "继续运动"]:
        return "CONTINUE_MOVE"
    if command_text_upper in ["STOP_MOVE", "停止运动"]:
        return "STOP_MOVE"
    if command_text_upper in ["GO_HOME_ALL", "全轴回零"]:
        return "GO_HOME_ALL"
    if command_text_upper in ["MONITOR", "状态监控"]:
        return "MONITOR"

    # --- 2. 带有可选/必需数值参数的命令 ---
    # SET_SPEED [<value>] / 设置速度 [<value>]
    # regex for: "SET_SPEED" or "设置速度", optionally followed by space and number
    match_speed = re.match(r"^(SET_SPEED|设置速度)\s*([\d\.\-]+)?$", command_text_upper)
    if match_speed:
        speed_value = match_speed.group(2) # group(2) is the optional value
        return f"SET_SPEED {speed_value}".strip() # .strip() handles case where speed_value is empty

    # TEST_WRITE_GV0 <value> / 测试写入GV0 <value>
    # regex for: "TEST_WRITE_GV0" or "测试写入GV0", followed by space and number
    match_test_gv0 = re.match(r"^(TEST_WRITE_GV0|测试写入GV0)\s+([\d\.\-]+)$", command_text_upper)
    if match_test_gv0:
        value = match_test_gv0.group(2) # group(2) is the value
        return f"TEST_WRITE_GV0 {value}"

    # --- 3. MOVE commands ---
    # MOVE J<axis_id> <angle> / 移动 J<axis_id> <angle>
    # regex for: "MOVE" or "移动", followed by "J" and digits, then space and number
    match_move_joint = re.match(r"^(MOVE|移动)\s+J(\d+)\s+([\d\.\-]+)$", command_text_upper)
    if match_move_joint:
        axis_id = match_move_joint.group(2) # group(2) is axis number (e.g., "1")
        angle = match_move_joint.group(3)   # group(3) is angle (e.g., "30")
        return f"MOVE J{axis_id} {angle}"

    # MOVE X/Y/Z/A/B/C <value> / 移动 X/Y/Z/A/B/C <value>
    # regex for: "MOVE" or "移动", followed by X/Y/Z/A/B/C, then space and number
    match_move_base = re.match(r"^(MOVE|移动)\s+([XYZABC])\s+([\d\.\-]+)$", command_text_upper)
    if match_move_base:
        axis_name = match_move_base.group(2) # group(2) is axis name (e.g., "X")
        value = match_move_base.group(3)     # group(3) is value (e.g., "100")
        return f"MOVE {axis_name} {value}"
    
    # --- 4. GO_HOME_J<axis_id> commands ---
    # GO_HOME_J<axis_id> / 回零 J<axis_id>
    # regex for: "GO_HOME_J" or "回零 J", followed by digits
    match_home_joint = re.match(r"^(GO_HOME_J|回零 J)(\d+)$", command_text_upper)
    if match_home_joint:
        axis_id = match_home_joint.group(2) # group(2) is axis number
        return f"GO_HOME_J{axis_id}"

    # 如果没有已知模式匹配，返回原始大写文本，这将在后续处理中被识别为错误。
    return command_text_upper

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

# --- 通用检查Modbus响应是否成功的方法 ---
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

# --- Modbus操作通用封装 ---
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
        return None
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
        return None
    except Exception as e:
        log.error(f"{operation_name} 过程中发生未知错误: {e}")
        return False

# --- 机器人Modbus控制封装 ---
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

def _send_incremental_offsets_modbus(client, offsets_payload, coordinate_type):
    """
    发送增量运动的偏移量到 GV200-GV205。
    offsets_payload: 字典 {轴ID或轴名称: 角度/距离}，例如 {1: 30} 或 {'X': 50}
    coordinate_type: 'joint' 或 'base_coords'
    """
    success_all = True
    
    # 初始化所有GV200-GV205为0.0，以确保每次增量运动都是独立的
    # Modbus地址从GV200开始 (400)，到GV205 (410)，共6个GV变量（12个寄存器）
    all_offsets_to_send = [0.0] * 6 # GV200-GV205

    # 根据传入的偏移量填充对应的位置
    for key, value in offsets_payload.items():
        if isinstance(key, int) and 1 <= key <= 6: # Joint offsets J1-J6
            gv_index = key - 1
            all_offsets_to_send[gv_index] = value
        elif isinstance(key, str) and key.upper() in ['X', 'Y', 'Z', 'A', 'B', 'C']: # Base coord offsets
            axis_map = {'X': 0, 'Y': 1, 'Z': 2, 'A': 3, 'B': 4, 'C': 5}
            gv_index = axis_map[key.upper()]
            all_offsets_to_send[gv_index] = value
        else:
            log.warning(f"未知轴或坐标类型 '{key}' 在增量运动偏移量中，将被忽略。")
            continue

    log.info(f"准备发送增量运动偏移量 ({coordinate_type}): {all_offsets_to_send}")

    # 将浮点数组转换为Modbus寄存器值并发送
    # 从GV200的低位地址开始写 (Modbus地址 400)
    start_modbus_address = 400 
    
    # 由于GV200-GV205是连续的，我们可以一次性写入12个寄存器
    registers_payload = []
    for val in all_offsets_to_send:
        registers_payload.extend(float_to_modbus_registers(val))
        
    op_name = f"设置增量运动偏移量 ({coordinate_type})"
    if not _execute_modbus_write_multiple(client, start_modbus_address, registers_payload, op_name):
        log.error("无法设置所有增量运动偏移量，运动可能不准确或失败。")
        success_all = False
    return success_all

def set_move_speed_modbus(speed): 
    """设置期望运动速度 (GV225 = speed)"""
    if not connect_modbus_client(): return False
    modbus_address = 450 # GV225 (Modbus 450,451)
    registers_to_write = float_to_modbus_registers(float(speed))
    return _execute_modbus_write_multiple(modbus_client, modbus_address, registers_to_write, "设置期望运动速度")

def start_incremental_move_modbus(coordinate_type):
    """
    启动增量运动，根据坐标类型发送不同的指令。
    coordinate_type: 'joint' (关节坐标系 0x40) 或 'base_coords' (基坐标系 0x41)
    """
    if not connect_modbus_client(): return False
    modbus_address = 440 # GV220_L 的Modbus地址

    if coordinate_type == 'joint':
        value = 0x40 # 按关节坐标增量运动
        op_name = "启动关节坐标系增量运动"
    elif coordinate_type == 'base_coords':
        value = 0x41 # 按基坐标增量运动
        op_name = "启动基坐标系增量运动"
    else:
        log.error(f"无效的运动坐标类型: {coordinate_type}")
        return False
          
    return _execute_modbus_write_single(modbus_client, modbus_address, value, op_name)

def go_home_all_modbus():
    """执行全轴回零功能 (GV222_H = 0x0B)"""
    if not connect_modbus_client(): return False
    modbus_address = 445 # GV222_H 的Modbus地址
    value = 0x0B         # 0x0B 表示全轴归零
    return _execute_modbus_write_single(modbus_client, modbus_address, value, "执行全轴回零")

def go_home_single_axis_modbus(axis_id):
    """执行单轴回零功能 (GV222_H = 0x00~0x05 for J1~J6)"""
    if not connect_modbus_client(): return False
    if not (1 <= axis_id <= 6):
        log.error(f"单轴回零的轴号无效: J{axis_id}。仅支持J1-J6。")
        return False
    
    modbus_address = 445 # GV222_H 的Modbus地址
    value = axis_id - 1  # J1 -> 0x00, J2 -> 0x01, ..., J6 -> 0x05
    op_name = f"执行单轴J{axis_id}回零"
    return _execute_modbus_write_single(modbus_client, modbus_address, value, op_name)


def pause_move_modbus():
    """暂停当前运动 (GV221_L = 0x01)"""
    if not connect_modbus_client(): return False
    modbus_address = 442 # GV221_L 的Modbus地址
    value = 0x01         # 0x01 表示暂停
    return _execute_modbus_write_single(modbus_client, modbus_address, value, "暂停运动")

def continue_move_modbus():
    """继续运动 (GV221_H = 0x01)"""
    if not connect_modbus_client(): return False
    modbus_address = 443 # GV221_H 的Modbus地址
    value = 0x01         # 0x01 表示继续
    return _execute_modbus_write_single(modbus_client, modbus_address, value, "继续运动")


def stop_move_modbus():
    """停止当前运动 (GV220_H = 0x01)"""
    if not connect_modbus_client(): return False
    modbus_address = 441 # GV220_H 的Modbus地址
    value = 0x01         # 0x01 表示停止
    return _execute_modbus_write_single(modbus_client, modbus_address, value, "停止运动")


def get_robot_status_modbus():
    """读取机器人当前状态：模式，运行状态，报警状态，GV0值"""
    if not connect_modbus_client(): return None
    
    status_data = {
        "mode": "未知",
        "run_status": "未知",
        "alarm_status": "未知",
        "alarm_code": 0, # 新增报警代码
        "gv0_value": None 
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
    # 报警信息在 GV281_L (Modbus地址 562)
    # 参数说明中 b0-急停报警, b1-伺服报警, b2-刹车异常报警, b3-算法报警, b4-获取编码器角度报警
    alarm_registers = _execute_modbus_read(modbus_client, 562, 1, "读取报警类型 (GV281_L)")
    if alarm_registers:
        alarm_code = alarm_registers[0]
        status_data["alarm_code"] = alarm_code
        if alarm_code == 0:
            status_data["alarm_status"] = "无报警"
        else:
            alarm_desc = []
            if (alarm_code & 0b00000001) != 0: alarm_desc.append("急停报警 (b0)")
            if (alarm_code & 0b00000010) != 0: alarm_desc.append("伺服报警 (b1)")
            if (alarm_code & 0b00000100) != 0: alarm_desc.append("刹车异常报警 (b2)")
            if (alarm_code & 0b00001000) != 0: alarm_desc.append("算法报警 (b3)")
            if (alarm_code & 0b00010000) != 0: alarm_desc.append("获取编码器角度报警 (b4)")
            status_data["alarm_status"] = f"有报警 ({hex(alarm_code)}): " + ", ".join(alarm_desc) if alarm_desc else f"有报警 ({hex(alarm_code)})"
            log.warning(f"机器人报警！代码: {hex(alarm_code)}，详情: {status_data['alarm_status']}")

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

def _wait_for_motion_completion(client, timeout=30, poll_interval=0.5):
    """
    内部阻塞函数：通过监测GV280_H (程序运行状态) 和 GV281_L (报警类型) 来判断运动是否完成。
    """
    log.info(f"等待当前运动完成 (最长 {timeout} 秒)...")
    start_time = time.time()
    
    # 1. 等待机器人进入“运行中”状态
    running_status_detected = False
    initial_poll_timeout = 5 # 额外给5秒时间确认运动是否启动

    poll_start_time = time.time()
    while time.time() - poll_start_time < initial_poll_timeout:
        status_info = get_robot_status_modbus() # 使用通用的状态获取函数
        if not status_info:
            log.error("等待运动启动时无法获取机器人状态，监测中断。")
            return False

        if status_info["alarm_code"] != 0:
            log.error(f"运动启动前检测到报警: {status_info['alarm_status']}。运动中止。")
            return False
        
        if status_info["run_status"] == "正在运行":
            running_status_detected = True
            break
        time.sleep(poll_interval)
    
    if not running_status_detected:
        log.warning(f"在 {initial_poll_timeout} 秒内机器人未进入 '正在运行' 状态。当前状态: {status_info['run_status']}.")
        log.warning("运动可能未启动或启动失败。")
        return False

    log.info("机器人已进入 '正在运行' 状态，等待运动完成...")

    # 2. 等待机器人返回“停止”状态
    while time.time() - start_time < timeout: # 使用整个操作的超时时间
        status_info = get_robot_status_modbus()
        if not status_info:
            log.error("等待运动完成时无法获取机器人状态，监测中断。")
            return False

        if status_info["alarm_code"] != 0:
            log.error(f"运动过程中检测到报警: {status_info['alarm_status']}。运动中止。")
            return False
            
        if status_info["run_status"] == "停止":
            log.info("机器人已返回 '停止' 状态。运动完成。")
            return True 

        time.sleep(poll_interval)

    log.warning(f"运动超时 ({timeout} 秒)。机器人可能仍在运行或未更新状态。请手动检查。")
    return False


# --- Flask 路由和API ---

@app.route('/')
def serve_index():
    """提供index.html文件"""
    return send_from_directory('.', 'index.html')

@app.route('/status', methods=['GET'])
def get_status_api():
    """提供机器人当前状态的API，供前端轮询"""
    robot_status_info = get_robot_status_modbus()
    if robot_status_info:
        return jsonify({"status": "success", "robot_status": robot_status_info})
    else:
        return jsonify({"status": "error", "message": "无法获取机器人状态。"})


@app.route('/command', methods=['POST'])
def handle_command():
    global current_speed_setting 
    data = request.get_json()
    commands_text = data.get('commands', '').strip() 

    log.info(f"收到指令批次:\n{commands_text}")

    response_messages = []
    overall_status = "success"
    batch_motion_started = False # 标记本次批处理是否有运动真正被启动

    # 连接到机器人Modbus客户端
    if not connect_modbus_client():
        return jsonify({"status": "error", "message": "无法连接到机器人Modbus。", "motion_started": False})

    # 预先设置机器人到自动模式，确保后续运动可以执行
    if not set_robot_auto_mode_modbus():
        return jsonify({"status": "error", "message": "无法切换机器人到自动模式，运动无法执行。", "motion_started": False})
    
    # 按行处理指令
    for line in commands_text.split('\n'):
        original_command_line = line.strip() # 保存原始行用于日志
        processed_command = normalize_command(original_command_line) # 先规范化指令
        
        if not processed_command:
            if original_command_line: # 如果原始行不为空，但规范化后为空，说明是无法识别的命令
                response_messages.append({"command": original_command_line, "status": "error", "message": "无法识别的指令格式。"})
                overall_status = "error"
            continue # 跳过空行或无法识别的行

        log.info(f"--- 处理规范化指令: {processed_command} ---")
        
        current_command_status = "success"
        current_command_message = ""
        motion_triggered_in_line = False # 标记当前行是否触发了运动且需要等待完成

        try:
            if processed_command == "AUTO_MODE":
                current_command_message = "机器人已处于自动模式 (已在批处理开始前设置)。"
            
            elif processed_command.startswith("MOVE J") or \
                 processed_command.startswith("MOVE X") or \
                 processed_command.startswith("MOVE Y") or \
                 processed_command.startswith("MOVE Z") or \
                 processed_command.startswith("MOVE A") or \
                 processed_command.startswith("MOVE B") or \
                 processed_command.startswith("MOVE C"):
                
                parts = processed_command.split()
                if len(parts) == 3 and parts[0] == "MOVE":
                    axis_part = parts[1]
                    value_str = parts[2]
                    
                    try:
                        value = float(value_str)
                        offsets_payload = {}
                        coordinate_type = 'joint' 
                        
                        if axis_part.startswith("J"): # Joint move
                            axis_id = int(axis_part[1:])
                            if 1 <= axis_id <= 6:
                                offsets_payload[axis_id] = value
                                current_command_message = f"已解析关节J{axis_id}增量运动参数为 {value} 度。"
                            else:
                                current_command_message = "MOVE指令中的轴号无效，应为J1到J6。"
                                current_command_status = "error"
                        else: # Base coordinate move (X,Y,Z,A,B,C)
                            axis_name = axis_part.upper()
                            if axis_name in ['X', 'Y', 'Z', 'A', 'B', 'C']:
                                offsets_payload[axis_name] = value
                                coordinate_type = 'base_coords'
                                current_command_message = f"已解析基坐标系 {axis_name} 轴增量运动参数为 {value}。"
                            else:
                                current_command_message = "MOVE指令中的坐标轴名称无效，应为X/Y/Z/A/B/C。"
                                current_command_status = "error"

                        if current_command_status == "success": 
                            # 1. 设置速度 (使用当前全局速度设置)
                            speed_set_ok = set_move_speed_modbus(current_speed_setting)
                            
                            # 2. 设置关节/基坐标系偏移量
                            offset_set_ok = _send_incremental_offsets_modbus(modbus_client, offsets_payload, coordinate_type)

                            if speed_set_ok and offset_set_ok:
                                # 3. 启动运动
                                start_ok = start_incremental_move_modbus(coordinate_type)
                                if start_ok:
                                    motion_triggered_in_line = True
                                    batch_motion_started = True 
                                else:
                                    current_command_message = f"启动运动失败。"
                                    current_command_status = "error"
                            else:
                                current_command_message = f"启动运动前设置参数失败。"
                                current_command_status = "error"

                    except ValueError:
                        current_command_message = "MOVE指令参数格式错误，请检查值是否为数字。"
                        current_command_status = "error"
                else:
                    current_command_message = "MOVE指令格式错误，应为 'MOVE <轴/坐标> <值>'。"
                    current_command_status = "error"

            elif processed_command.startswith("SET_SPEED"):
                parts = processed_command.split()
                speed_val = DEFAULT_SPEED 
                if len(parts) == 2: 
                    try:
                        speed_val = float(parts[1])
                    except ValueError:
                        current_command_message = f"SET_SPEED指令参数格式错误，速度值应为数字，将使用默认值 {DEFAULT_SPEED}。"
                        current_command_status = "warning" 
                elif len(parts) == 1: 
                    current_command_message = f"SET_SPEED指令无参数，将使用默认值 {DEFAULT_SPEED}。"
                else: 
                    current_command_message = f"SET_SPEED指令格式错误，将使用默认值 {DEFAULT_SPEED}。"
                    current_command_status = "warning"
                
                current_speed_setting = speed_val 
                if current_command_status != "warning": 
                     current_command_message = f"已设置运动速度参数为 {current_speed_setting}。"
                
            elif processed_command == "MONITOR":
                current_command_message = "前端状态轮询已触发。"
                
            elif processed_command.startswith("TEST_WRITE_GV0"):
                parts = processed_command.split()
                if len(parts) == 2:
                    try:
                        value = float(parts[1])
                        success = write_gv0_test_value_modbus(value)
                        current_command_message = f"已向GV0写入测试值 {value}。" if success else "向GV0写入测试值失败。"
                        if not success: current_command_status = "error"
                    except ValueError:
                        current_command_message = "TEST_WRITE_GV0指令参数格式错误，值应为数字。"
                        current_command_status = "error"
                else:
                    current_command_message = "TEST_WRITE_GV0指令格式错误，应为 'TEST_WRITE_GV0 <值>'。"
                    current_command_status = "error"
            
            elif processed_command == "GO_HOME_ALL":
                success = go_home_all_modbus()
                current_command_message = "已发送全轴回零指令。" if success else "发送全轴回零指令失败。"
                if success: motion_triggered_in_line = True 
                if not success: current_command_status = "error"

            elif processed_command.startswith("GO_HOME_J"):
                parts = processed_command.split('J')
                if len(parts) == 2:
                    try:
                        axis_id = int(parts[1])
                        if 1 <= axis_id <= 6:
                            success = go_home_single_axis_modbus(axis_id)
                            current_command_message = f"已发送J{axis_id}单轴回零指令。" if success else f"发送J{axis_id}单轴回零指令失败。"
                            if success: motion_triggered_in_line = True
                            if not success: current_command_status = "error"
                        else:
                            current_command_message = "GO_HOME_J指令中的轴号无效，应为J1到J6。"
                            current_command_status = "error"
                    except ValueError:
                        current_command_message = "GO_HOME_J指令格式错误，轴号应为数字。"
                        current_command_status = "error"
                else:
                    current_command_message = "GO_HOME_J指令格式错误，应为 'GO_HOME_J<轴号>'。"
                    current_command_status = "error"

            elif processed_command == "PAUSE_MOVE":
                success = pause_move_modbus()
                current_command_message = "已发送暂停运动指令。" if success else "发送暂停运动指令失败。"
                if not success: current_command_status = "error"
            
            elif processed_command == "CONTINUE_MOVE": # New: Handle CONTINUE_MOVE
                success = continue_move_modbus()
                current_command_message = "已发送继续运动指令。" if success else "发送继续运动指令失败。"
                if not success: current_command_status = "error"

            elif processed_command == "STOP_MOVE":
                success = stop_move_modbus()
                current_command_message = "已发送停止运动指令。" if success else "发送停止运动指令失败。"
                if not success: current_command_status = "error"
            
            else: # 未知或手动START_MOVE
                current_command_message = "未知指令或指令格式错误。"
                current_command_status = "error"

        except Exception as e:
            current_command_message = f"处理指令 '{original_command_line}' 时发生异常: {e}"
            current_command_status = "error"
        
        response_messages.append({"command": original_command_line, "status": current_command_status, "message": current_command_message})
        
        if current_command_status == "error":
            overall_status = "error" # 如果任何一个指令失败，整体状态就是error
            break # 出现错误立即停止批处理
        
        # 如果当前指令是运动指令，等待其完成
        if motion_triggered_in_line and overall_status != "error":
            log.info(f"等待 '{original_command_line}' 运动完成...")
            motion_completed_successfully = _wait_for_motion_completion(modbus_client)
            if not motion_completed_successfully:
                overall_status = "error"
                response_messages.append({"command": f"等待 '{original_command_line}' 完成", "status": "error", "message": "运动未完成或发生报警，批处理中断。"})
                break # 运动未完成，中断整个批处理

    # 获取机器人最新状态
    current_robot_status_info = get_robot_status_modbus()

    # 准备最终响应给前端
    final_response = {
        "status": overall_status,
        "message": "指令批次处理完成。" if overall_status == "success" else "指令批次处理存在错误或中断。",
        "detailed_results": response_messages,
        "motion_started": batch_motion_started, # 标记是否有运动被真正启动
        "robot_status": current_robot_status_info
    }

    return jsonify(final_response)

# Flask 应用启动时运行的函数
if __name__ == '__main__':
    app.run(debug=True, host=SERVER_HOST, port=SERVER_PORT)
    # host='0.0.0.0'允许从任何IP访问
