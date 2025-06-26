import json
import os
import sys
from flask import Flask, request, jsonify, send_from_directory
# CORS 不再需要，因为前后端现在是同源的
# from flask_cors import CORS 
from pymodbus.client import ModbusTcpClient 
from pymodbus.exceptions import ModbusException
import struct
import time
import logging
import re
import threading
import webbrowser

# LLM 相关的导入
from openai import OpenAI
from openai import APIStatusError, APIConnectionError, APITimeoutError


# 配置日志，设置为INFO级别，便于查看关键操作，DEBUG级别用于更详细的Modbus通信日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

def is_frozen():
    """ 检查程序是否被 PyInstaller 打包 """
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


def get_project_root():
    """
    获取项目的根目录，智能适应开发环境和打包后的环境。
    - 在开发模式下(运行.py)，这是 `backend` 目录的上一级。
    - 在打包后的程序中(.exe)，这是可执行文件所在的目录。
    """
    if is_frozen():
        return os.path.dirname(sys.executable)
    else:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


# --- Flask 应用初始化 ---
static_dir = None
if is_frozen():
    # 在打包后的程序中，静态文件位于_MEIPASS临时目录内
    static_dir = os.path.join(sys._MEIPASS, 'frontend', 'dist')
else:
    # 在开发模式下，静态文件位于项目根目录下的 'frontend/dist'
    static_dir = os.path.join(get_project_root(), 'frontend', 'dist')

log.info(f"Flask 静态文件目录设置为: {static_dir}")
app = Flask(__name__, static_folder=static_dir)


# --- 全局变量和配置加载 ---

modbus_client = None

def load_config():
    """
    加载 config.json 文件。
    它总是相对于项目的根目录（对于.exe是其所在目录，对于.py是其所在目录）
    """
    if is_frozen():
        config_path = os.path.join(get_project_root(), 'config.json')
    else:
        config_path = os.path.join(get_project_root(), 'backend','config.json')
    log.info(f"正在从以下路径加载配置文件: {config_path}")
        

    if not os.path.exists(config_path):
        log.critical(f"错误：配置文件 '{config_path}' 未找到。请确保 config.json 与程序在同一目录下。程序退出。")
        sys.exit(1)
        
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

CONFIG = load_config()
ROBOT_IP = CONFIG.get('robot', {}).get('ip')
ROBOT_PORT = CONFIG.get('robot', {}).get('port', 502)
SLAVE_ID = CONFIG.get('robot', {}).get('slave_id', 1)
DEFAULT_SPEED = CONFIG.get('motion', {}).get('default_speed', 100.0)
SERVER_HOST = CONFIG.get('server', {}).get('host', '127.0.0.1')
SERVER_PORT = CONFIG.get('server', {}).get('port', 5000)
LLM_CONFIG = CONFIG.get('llm_config', {})
current_speed_setting = DEFAULT_SPEED
LLM_MODEL_NAME = CONFIG.get('llm_config', {}).get('model_name')

# --- LLM 客户端初始化 ---
llm_client = None
if LLM_CONFIG.get('api_key'):
    try:
        llm_client = OpenAI(api_key=LLM_CONFIG['api_key'], base_url=LLM_CONFIG.get('api_base_url'))
        log.info("LLM 客户端初始化成功。")
    except Exception as e:
        log.error(f"LLM 客户端初始化失败: {e}")
else:
    log.warning("未配置 LLM API Key，自然语言控制不可用。")


# --- 全局运动参数设置 ---
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

# --- LLM API 调用和解析函数 ---
LLM_SYSTEM_PROMPT = """
你是一个机器人指令解析器，你的任务是将用户的自然语言指令转化为一个结构化的JSON数组，其中包含机器人可以执行的操作序列。
请严格按照以下规则和JSON格式输出，不要包含任何额外的文本或解释。


**输出格式:**
你的输出必须是一个JSON对象，包含一个`commands`数组和一个可选的`error`字段。
```json
{
  "commands": [
    { "command_type": "<类型>", "parameters": { ... } },
    { "command_type": "<类型>", "parameters": { ... } }
  ],
  "error": null // 如果解析成功，error为null
}
```

**支持的命令类型 (command_type) 及其参数 (parameters):**

1.  **SET_SPEED**: 设置机器人运动速度。
    * `parameters`: `{"speed_value": <float>}` (例如: `{"speed_value": 100.0}`)
    * 如果用户未指定速度，请使用默认值 `100.0`。

2.  **MOVE_JOINT**: 关节增量运动。
    * `parameters`: `{"axis_id": <int>, "angle": <float>}`
        * `axis_id`: 1到6的整数，表示关节J1到J6。
        * `angle`: 浮点数，表示移动的度数。
    * 例如: `{"axis_id": 1, "angle": 30.0}`

3.  **MOVE_BASE**: 基坐标系增量运动 (直线或姿态)。
    * `parameters`: `{"axis_name": <str>, "value": <float>}`
        * `axis_name`: 字符串 "X", "Y", "Z", "A", "B", "C"。
        * `value`: 浮点数，表示X/Y/Z的距离(毫米)或A/B/C的角度(度)。
    * 例如: `{"axis_name": "X", "value": 50.0}`

4.  **GO_HOME_JOINT**: 单轴回零。
    * `parameters`: `{"axis_id": <int>}` (1到6的整数)。
    * 例如: `{"axis_id": 1}`

5.  **GO_HOME_ALL**: 全轴回零。
    * `parameters`: `{}` (空对象)

6.  **PAUSE_MOVE**: 暂停当前运动。
    * `parameters`: `{}` (空对象)

7.  **CONTINUE_MOVE**: 继续暂停的运动。
    * `parameters`: `{}` (空对象)

8.  **STOP_MOVE**: 停止当前运动。
    * `parameters`: `{}` (空对象)

9.  **MONITOR**: 监控机器人状态 (不执行动作，仅获取最新状态)。
    * `parameters`: `{}` (空对象)

10. **TEST_WRITE_GV0**: 向GV0写入一个测试值。
    * `parameters`: `{"value": <float>}`
    * 例如: `{"value": 123.45}`

**错误处理:**
如果用户的指令无法理解，或者解析出的参数不合法（例如轴号超出范围，非数字值等），请返回如下JSON，并在`error`字段说明错误类型，`commands`数组为空。
```json
{
  "commands": [],
  "error": "PARSE_ERROR",
  "message": "无法理解您的指令或参数不合法，请提供更清晰的描述，并确保参数在有效范围内。"
}
```

**重要提示:**
* 所有数值参数必须是浮点数 (float)。
* `axis_id` 必须是整数。
* 如果用户未指定 `SET_SPEED` 的速度值，请在JSON中自动填充 `100.0`。
* 规定X轴方向为前后运动，Y轴方向为左右运动，Z轴方向为上下运动。
* 规定X轴正方向为后，X轴负方向为前；Y轴正方向为左，Y轴负方向为右；Z轴正方向为上，Z轴负方向为下。
* 如果用户指令想沿坐标系运动，但未指定方向，则默认沿坐标轴正反向运动
* 请确保在处理连续指令时，保持合理的执行顺序。
* 不要返回任何Markdown格式，只返回纯JSON。

**示例1:**

用户输入: "让关节1转动30度，然后把速度设为50，再让X轴前进100毫米，最后全轴回零。"
期望JSON:
```json
{
  "commands": [
    { "command_type": "MOVE_JOINT", "parameters": {"axis_id": 1, "angle": 30.0} },
    { "command_type": "SET_SPEED", "parameters": {"speed_value": 50.0} },
    { "command_type": "MOVE_BASE", "parameters": {"axis_name": "X", "value": 100.0} },
    { "command_type": "GO_HOME_ALL", "parameters": {} }
  ],
  "error": null
}
```

**示例2:**

用户输入: "让机器人向左运动10cm，然后把速度设为50，再让X轴运动100毫米，最后全轴回零。"
期望JSON:
```json
{
  "commands": [
    { "command_type": "MOVE_BASE", "parameters": {"axis_name": "Y", "value": -100.0} },
    { "command_type": "SET_SPEED", "parameters": {"speed_value": 50.0} },
    { "command_type": "MOVE_BASE", "parameters": {"axis_name": "X", "value": 100.0} },
    { "command_type": "GO_HOME_ALL", "parameters": {} }
  ],
  "error": null
}
```
"""

def call_llm_api(user_query):
    """
    调用 DeepSeek LLM API 解析自然语言指令。
    返回解析后的结构化命令列表或错误信息。
    """
    if not llm_client:
        log.error("LLM 客户端未初始化。请检查 API Key 配置。")
        return {"commands": [], "error": "LLM_NOT_CONFIGURED", "message": "后端LLM服务未正确配置或API Key缺失。"}

    # 检查模型名称是否已在设定档中定义，若未定义则返回清晰的错误讯息
    if not LLM_MODEL_NAME:
        log.error("LLM 模型名称 (model_name) 未在 config.json 的 llm_config 中配置。")
        return {"commands": [], "error": "LLM_MODEL_NOT_CONFIGURED", "message": "LLM模型名称未配置，请检查config.json文件。"}

    messages = [
        {"role": "system", "content": LLM_SYSTEM_PROMPT},
        {"role": "user", "content": user_query}
    ]

    try:
        log.info(f"调用 LLM API 进行解析，查询: '{user_query[:50]}...'")
        chat_completion = llm_client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=messages,
            response_format={"type": "json_object"} # 明确要求JSON输出
        )
        
        llm_response_content = chat_completion.choices[0].message.content
        log.debug(f"LLM 原始响应: {llm_response_content}")

        # 尝试解析LLM返回的JSON
        parsed_llm_output = json.loads(llm_response_content)
        
        # 验证LLM返回的结构
        if "commands" in parsed_llm_output and isinstance(parsed_llm_output["commands"], list):
            # 可以在这里对LLM解析出的commands进行进一步的参数合法性校验
            # 例如，确保axis_id是1-6，value是数字等
            return parsed_llm_output
        else:
            log.error(f"LLM 返回的JSON结构不符合预期: {llm_response_content}")
            return {"commands": [], "error": "LLM_PARSE_FAIL", "message": "LLM返回了不符合预期的JSON结构。"}

    except json.JSONDecodeError as e:
        log.error(f"LLM 返回的不是有效JSON: {llm_response_content}。错误: {e}")
        return {"commands": [], "error": "LLM_INVALID_JSON", "message": "LLM未能返回有效JSON，请尝试更清晰的指令。"}
    except (APIStatusError, APIConnectionError, APITimeoutError) as e:
        log.error(f"调用 DeepSeek API 失败: {e}")
        return {"commands": [], "error": "LLM_API_ERROR", "message": f"LLM服务连接失败或返回错误: {e.status_code if hasattr(e, 'status_code') else '未知错误'}"}
    except Exception as e:
        log.error(f"调用 LLM 过程中发生未知异常: {e}")
        return {"commands": [], "error": "LLM_UNKNOWN_ERROR", "message": f"LLM解析过程中发生未知错误: {e}"}

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
        return None

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
        return None

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
        value = 0x41 # 按基坐标系增量运动
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

@app.route('/api/status', methods=['GET'])
def get_status_api():
    """提供机器人当前状态的API，供前端轮询"""
    robot_status_info = get_robot_status_modbus()
    if robot_status_info:
        return jsonify({"status": "success", "robot_status": robot_status_info})
    else:
        return jsonify({"status": "error", "message": "无法获取机器人状态。"})


@app.route('/api/command', methods=['POST'])
def handle_command():
    global current_speed_setting 
    data = request.get_json()
    user_input_commands_text = data.get('commands', '').strip() 

    log.info(f"收到用户指令批次:\n{user_input_commands_text}")

    response_messages = [] # 用于记录每条子指令的执行结果
    overall_status = "success"
    batch_motion_started = False # 标记本次批处理是否有运动真正被启动
    
    parsed_commands_to_execute = [] # 存储最终要执行的结构化命令列表

    # 连接到机器人Modbus客户端
    if not connect_modbus_client():
        return jsonify({"status": "error", "message": "无法连接到机器人Modbus。", "motion_started": False})

    # 预先设置机器人到自动模式，确保后续运动可以执行
    if not set_robot_auto_mode_modbus():
        return jsonify({"status": "error", "message": "无法切换机器人到自动模式，运动无法执行。", "motion_started": False})
    
    # --- 阶段1：尝试解析严格格式指令 (优先处理) ---
    is_strict_format_batch = False
    temp_strict_parsed_commands = [] # 临时存放严格解析的命令

    for line in user_input_commands_text.split('\n'):
        original_line_strip = line.strip()
        if not original_line_strip: continue

        normalized_strict_command = normalize_command(original_line_strip)
        
        # 判断是否是严格格式指令 (通过规范化函数是否能将其转换为标准的英文指令格式)
        # 简单判断：如果规范化后的指令以已知命令类型开头且不含无法识别的字符，则认为是严格格式
        # 复杂模式的判断会更复杂，这里仅为示例
        is_known_strict_format = False
        for cmd_type in ["AUTO_MODE", "SET_SPEED", "MOVE", "GO_HOME", "PAUSE_MOVE", "CONTINUE_MOVE", "STOP_MOVE", "MONITOR", "TEST_WRITE_GV0"]:
            if normalized_strict_command.startswith(cmd_type):
                is_known_strict_format = True
                break
        
        if is_known_strict_format:
            # 对于严格模式，我们依然需要提取参数，这里简化处理，直接让LLM解析函数处理
            # 传递一个LLM解析函数能接受的简单结构，稍后_execute_parsed_command_action会调用LLM
            # 这里是为了兼容两种流程使用同一个执行器
            # 实际上在_execute_parsed_command_action内部会再次解析这个string
            temp_strict_parsed_commands.append({
                "command_type": "STRICT_FORMAT_PLACEHOLDER", # 标记这是严格格式，需要特殊处理
                "parameters": {"original_command_string": original_line_strip}
            })
        else:
            # 如果任何一行不符合严格格式，则整个批次都视为自然语言
            is_strict_format_batch = False 
            break # 只要有一行不严格，就跳出，转为LLM处理
    else: # 如果循环没有被break
        is_strict_format_batch = True
        parsed_commands_to_execute = temp_strict_parsed_commands

    # --- 阶段2：如果不是严格格式，使用 LLM 解析自然语言 ---
    if not is_strict_format_batch:
        log.info("用户输入不符合严格格式，尝试使用 LLM 解析自然语言指令...")
        if not llm_client:
            return jsonify({"status": "error", "message": "未配置LLM服务，无法处理自然语言指令。", "motion_started": False})

        llm_parse_result = call_llm_api(user_input_commands_text)
        
        if llm_parse_result["error"]:
            overall_status = "error"
            response_messages.append({
                "command": user_input_commands_text,
                "status": "error",
                "message": f"LLM解析失败: {llm_parse_result.get('message', '未知错误')} (代码: {llm_parse_result.get('error', 'UNKNOWN_ERROR')})"
            })
            log.error(f"LLM 解析失败: {llm_parse_result.get('message', '未知错误')}")
        else:
            log.info(f"LLM 解析成功，得到 {len(llm_parse_result['commands'])} 条指令。")
            parsed_commands_to_execute = llm_parse_result["commands"]
            # 检查LLM解析后的指令是否有效
            if not parsed_commands_to_execute:
                 overall_status = "error"
                 response_messages.append({
                    "command": user_input_commands_text,
                    "status": "warning",
                    "message": "LLM未能解析出任何可执行指令，请尝试更清晰的描述。"
                })

# --- 阶段3：执行解析后的指令序列 ---
    if overall_status == "success": # 只有LLM或严格解析成功后才执行
        for cmd_data in parsed_commands_to_execute:
            original_command_line = "" # 为当前步骤的原始指令行创建一个变量

            # 对于 STRICT_FORMAT_PLACEHOLDER，需要再次调用 normalize_command
            if cmd_data.get("command_type") == "STRICT_FORMAT_PLACEHOLDER":
                original_command_line = cmd_data["parameters"]["original_command_string"]
                executable_cmd_str = normalize_command(original_command_line) 
                log.info(f"执行严格格式指令: '{executable_cmd_str}'")
                
                # 在调用时，我们将单行的严格指令作为“原始指令”传递
                execute_result_status, motion_triggered_in_step = \
                    _execute_parsed_command_action(modbus_client, {"command_type": "STRICT_EXEC", "parameters": {"normalized_command_string": executable_cmd_str}}, response_messages, original_command_line)
            else:
                # 对于LLM解析的指令，其“原始指令”是整个用户输入文本块
                original_command_line = user_input_commands_text
                log.info(f"执行LLM解析指令: '{cmd_data.get('command_type')}' parameters: {cmd_data.get('parameters')}")
                
                # 【修正點 1】: 使用正确的 'user_input_commands_text' 变量
                execute_result_status, motion_triggered_in_step = \
                    _execute_parsed_command_action(modbus_client, cmd_data, response_messages, user_input_commands_text) 

            if execute_result_status == "error":
                overall_status = "error"
                break # 某个指令执行失败，中断整个批处理

            if motion_triggered_in_step:
                batch_motion_started = True
                
                # 【修正點 2】: 在日志记录中使用正确的变量 'original_command_line'
                # 这里我们使用 'original_command_line'，它代表了触发本次运动的具体指令行（严格模式）或整个指令块（LLM模式）
                log.info(f"等待当前运动完成 (来自 {original_command_line})...")
                motion_completed_successfully = _wait_for_motion_completion(modbus_client)
                
                if not motion_completed_successfully:
                    overall_status = "error"
                    # 【修正點 3】: 在错误回报中使用正确的变量
                    response_messages.append({"command": original_command_line, "status": "error", "message": "运动未完成或发生报警，批处理中断。"})
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


def _execute_parsed_command_action(client, parsed_command_data, response_messages_list, original_command_line):
    """
    这是一个核心执行函数，它根据解析出的结构化命令类型来调用相应的Modbus函数。
    它现在也处理STRICT_EXEC类型，直接解析其内部的字符串指令。
    返回 (执行状态, 是否触发了运动且需要等待完成)
    """
    command_type = parsed_command_data.get("command_type")
    parameters = parsed_command_data.get("parameters", {})
    
    current_status = "success"
    current_message = f"指令 '{original_command_line}' 执行成功。" # Use original line for message
    motion_triggered = False

    try:
        # 特殊处理 STRICT_EXEC 类型，它内部包含一个严格格式的字符串指令
        if command_type == "STRICT_EXEC":
            normalized_cmd_str = parameters.get("normalized_command_string", "")
            # 重新解析严格格式指令，进行实际的执行
            return _execute_strict_command_action(client, normalized_cmd_str, response_messages_list, original_command_line)

        # 以下是LLM解析出的各种结构化命令的执行逻辑
        elif command_type == "AUTO_MODE":
            success = set_robot_auto_mode_modbus()
            current_message = "机器人已尝试切换到自动模式。" if success else "切换自动模式失败。"
            if not success: current_status = "error"
        
        elif command_type == "SET_SPEED":
            speed_val = parameters.get("speed_value", DEFAULT_SPEED) # Use default if not provided by LLM
            # Update global speed setting
            global current_speed_setting 
            current_speed_setting = speed_val
            success = set_move_speed_modbus(current_speed_setting)
            current_message = f"已设置运动速度参数为 {current_speed_setting}。" if success else "设置运动速度失败。"
            if not success: current_status = "error"

        elif command_type in ["MOVE_JOINT", "MOVE_BASE"]:
            offsets_payload = {}
            coordinate_type = 'joint' # 默认设为关节坐标

            if command_type == "MOVE_JOINT":
                # 对于关节运动，从 'axis_id' 和 'angle' 获取参数
                axis_id = parameters.get("axis_id")
                angle = parameters.get("angle") # <-- 从 'angle' 获取值

                if not isinstance(axis_id, int) or not (1 <= axis_id <= 6):
                    raise ValueError(f"关节轴号无效或缺失: J{axis_id}。")
                if angle is None: # 增加对 None 值的检查
                    raise ValueError("MOVE_JOINT 指令缺少 'angle' 参数。")
                
                offsets_payload[axis_id] = float(angle) # <-- 使用 angle 变量
                current_message = f"已设置关节J{axis_id}增量运动参数为 {angle} 度。"
                
            else: # command_type == "MOVE_BASE"
                # 对于基坐标系运动，从 'axis_name' 和 'value' 获取参数
                axis_name = parameters.get("axis_name")
                value = parameters.get("value") # <-- 从 'value' 获取值

                if not isinstance(axis_name, str) or axis_name.upper() not in ['X', 'Y', 'Z', 'A', 'B', 'C']:
                    raise ValueError(f"基坐标轴名称无效或缺失: {axis_name}。")
                if value is None: # 增加对 None 值的检查
                    raise ValueError(f"MOVE_BASE 指令缺少 'value' 参数。")

                offsets_payload[axis_name.upper()] = float(value) # <-- 使用 value 变量
                coordinate_type = 'base_coords'
                current_message = f"已设置基坐标系 {axis_name} 轴增量运动参数为 {value}。"

            # 启动运动的后续逻辑保持不变
            speed_set_ok = set_move_speed_modbus(current_speed_setting)
            offset_set_ok = _send_incremental_offsets_modbus(client, offsets_payload, coordinate_type)

            if speed_set_ok and offset_set_ok:
                start_ok = start_incremental_move_modbus(coordinate_type)
                if start_ok:
                    current_message += " 运动已启动。"
                    motion_triggered = True
                else:
                    current_message += " 启动运动失败。"
                    current_status = "error"
            else:
                current_message += " 启动运动前设置参数失败。"
                current_status = "error"

        elif command_type == "GO_HOME_JOINT":
            axis_id = parameters.get("axis_id")
            if not isinstance(axis_id, int) or not (1 <= axis_id <= 6):
                raise ValueError(f"关节轴号无效或缺失: J{axis_id}。")
            success = go_home_single_axis_modbus(axis_id)
            current_message = f"已发送J{axis_id}单轴回零指令。" if success else f"发送J{axis_id}单轴回零指令失败。"
            if success: motion_triggered = True
            if not success: current_status = "error"

        elif command_type == "GO_HOME_ALL":
            success = go_home_all_modbus()
            current_message = "已发送全轴回零指令。" if success else "发送全轴回零指令失败。"
            if success: motion_triggered = True
            if not success: current_status = "error"

        elif command_type == "PAUSE_MOVE":
            success = pause_move_modbus()
            current_message = "已发送暂停运动指令。" if success else "发送暂停运动指令失败。"
            if not success: current_status = "error"
        
        elif command_type == "CONTINUE_MOVE":
            success = continue_move_modbus()
            current_message = "已发送继续运动指令。" if success else "发送继续运动指令失败。"
            if not success: current_status = "error"

        elif command_type == "STOP_MOVE":
            success = stop_move_modbus()
            current_message = "已发送停止运动指令。" if success else "发送停止运动指令失败。"
            if not success: current_status = "error"

        elif command_type == "MONITOR":
            current_message = "状态监控指令 (前端将轮询状态)。"

        elif command_type == "TEST_WRITE_GV0":
            value = parameters.get("value")
            if value is None: raise ValueError("GV0写入值缺失。")
            success = write_gv0_test_value_modbus(float(value))
            current_message = f"已向GV0写入测试值 {value}。" if success else "向GV0写入测试值失败。"
            if not success: current_status = "error"

        else:
            current_message = f"未知或不支持的指令类型: {command_type}。"
            current_status = "error"

    except ValueError as e:
        current_message = f"指令参数错误: {e}。"
        current_status = "error"
    except Exception as e:
        log.error(f"执行指令 '{original_command_line}' (类型: {command_type}) 时发生异常: {e}", exc_info=True)
        current_message = f"执行指令时发生内部错误: {e}。"
        current_status = "error"

    response_messages_list.append({"command": original_command_line, "status": current_status, "message": current_message})
    
    return current_status, motion_triggered

def _execute_strict_command_action(client, normalized_command_string, response_messages_list, original_command_line):
    """
    这个辅助函数专门用于执行由normalize_command解析出来的严格格式指令字符串。
    它将解析这些字符串并调用对应的Modbus函数。
    """
    global current_speed_setting 
    
    parts = normalized_command_string.split()
    command_type_strict = parts[0]
    
    current_status = "success"
    current_message = f"指令 '{original_command_line}' 执行成功。"
    motion_triggered = False

    try:
        if command_type_strict == "AUTO_MODE":
            success = set_robot_auto_mode_modbus()
            current_message = "机器人已尝试切换到自动模式。" if success else "切换自动模式失败。"
            if not success: current_status = "error"
        
        elif command_type_strict == "SET_SPEED":
            speed_val = DEFAULT_SPEED 
            if len(parts) == 2: 
                try:
                    speed_val = float(parts[1])
                except ValueError:
                    current_message = f"SET_SPEED指令参数格式错误，速度值应为数字，将使用默认值 {DEFAULT_SPEED}。"
                    current_status = "warning" 
            
            current_speed_setting = speed_val 
            if current_status != "warning": 
                 current_message = f"已设置运动速度参数为 {current_speed_setting}。"
            
            success = set_move_speed_modbus(current_speed_setting)
            if not success: 
                current_status = "error"
                current_message = "设置运动速度失败。"

        elif command_type_strict == "MONITOR":
            current_message = "前端状态轮询已触发。"
            
        elif command_type_strict == "TEST_WRITE_GV0":
            if len(parts) == 2:
                try:
                    value = float(parts[1])
                    success = write_gv0_test_value_modbus(value)
                    current_message = f"已向GV0写入测试值 {value}。" if success else "向GV0写入测试值失败。"
                    if not success: current_status = "error"
                except ValueError:
                    current_message = "TEST_WRITE_GV0指令参数格式错误，值应为数字。"
                    current_command_status = "error"
            else:
                current_message = "TEST_WRITE_GV0指令格式错误，应为 'TEST_WRITE_GV0 <值>'。"
                current_status = "error"
        
        elif command_type_strict == "GO_HOME_ALL":
            success = go_home_all_modbus()
            current_message = "已发送全轴回零指令。" if success else "发送全轴回零指令失败。"
            if success: motion_triggered = True 
            if not success: current_status = "error"

        elif command_type_strict == "GO_HOME_J":
            axis_id = int(parts[1]) # axis_id is part[1] for GO_HOME_J<id>
            if not (1 <= axis_id <= 6):
                current_message = "GO_HOME_J指令中的轴号无效，应为J1到J6。"
                current_status = "error"
            else:
                success = go_home_single_axis_modbus(axis_id)
                current_message = f"已发送J{axis_id}单轴回零指令。" if success else f"发送J{axis_id}单轴回零指令失败。"
                if success: motion_triggered = True
                if not success: current_status = "error"

        elif command_type_strict == "PAUSE_MOVE":
            success = pause_move_modbus()
            current_message = "已发送暂停运动指令。" if success else "发送暂停运动指令失败。"
            if not success: current_status = "error"
        
        elif command_type_strict == "CONTINUE_MOVE": 
            success = continue_move_modbus()
            current_message = "已发送继续运动指令。" if success else "发送继续运动指令失败。"
            if not success: current_status = "error"

        elif command_type_strict == "STOP_MOVE":
            success = stop_move_modbus()
            current_message = "已发送停止运动指令。" if success else "发送停止运动指令失败。"
            if not success: current_status = "error"
        
        elif command_type_strict == "MOVE":
            # MOVE指令需要处理 J<id> 或 X/Y/Z/A/B/C
            axis_part = parts[1]
            value = float(parts[2])
            offsets_payload = {}
            coordinate_type = 'joint' # Default for MOVE Jx
            
            if axis_part.startswith("J"): # Joint move
                axis_id = int(axis_part[1:])
                if not (1 <= axis_id <= 6):
                    raise ValueError("MOVE指令中的轴号无效，应为J1到J6。")
                offsets_payload[axis_id] = value
                current_message = f"已解析关节J{axis_id}增量运动参数为 {value} 度。"
            else: # Base coordinate move (X,Y,Z,A,B,C)
                axis_name = axis_part.upper()
                if axis_name not in ['X', 'Y', 'Z', 'A', 'B', 'C']:
                    raise ValueError("MOVE指令中的坐标轴名称无效，应为X/Y/Z/A/B/C。")
                offsets_payload[axis_name] = value
                coordinate_type = 'base_coords'
                current_message = f"已解析基坐标系 {axis_name} 轴增量运动参数为 {value}。"

            # 启动运动
            speed_set_ok = set_move_speed_modbus(current_speed_setting)
            offset_set_ok = _send_incremental_offsets_modbus(client, offsets_payload, coordinate_type)

            if speed_set_ok and offset_set_ok:
                start_ok = start_incremental_move_modbus(coordinate_type)
                if start_ok:
                    current_message += " 运动已启动。"
                    motion_triggered = True
                else:
                    current_message += " 启动运动失败。"
                    current_status = "error"
            else:
                current_message += " 启动运动前设置参数失败。"
                current_status = "error"
        
        else:
            current_message = f"未知指令或指令格式错误: '{normalized_command_string}'。"
            current_status = "error"

    except ValueError as e:
        current_message = f"指令 '{normalized_command_string}' 参数错误: {e}。"
        current_status = "error"
    except Exception as e:
        log.error(f"执行严格指令 '{normalized_command_string}' 时发生异常: {e}", exc_info=True)
        current_message = f"执行指令时发生内部错误: {e}。"
        current_status = "error"
    
    # response_messages_list 已经在 handle_command 中处理，这里只返回状态和是否触发运动
    return current_status, motion_triggered

# --- 服务 Vue 前端的 Catch-all 路由 ---
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_vue_app(path):
    """托管 Vue 应用的静态文件和主页"""
    if not os.path.exists(app.static_folder):
        log.error(f"静态文件目录不存在: {app.static_folder}")
        return "Frontend files not found. Please ensure the 'frontend/dist' directory exists.", 404
        
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        # 对于根路径或未找到的路径，返回 index.html
        index_path = os.path.join(app.static_folder, 'index.html')
        if not os.path.exists(index_path):
            log.error(f"主页文件 index.html 不存在于: {app.static_folder}")
            return "Application entry point not found.", 404
        return send_from_directory(app.static_folder, 'index.html')

# --- 应用启动 ---
def open_browser():
    """自动打开浏览器"""
    host = '127.0.0.1' if SERVER_HOST == '0.0.0.0' else SERVER_HOST
    webbrowser.open_new_tab(f"http://{host}:{SERVER_PORT}")

if __name__ == '__main__':
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        threading.Timer(1.25, open_browser).start()
    
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False)
