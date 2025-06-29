# backend/routes.py

import logging
from flask import Blueprint, request, jsonify, current_app
from .robot_controller import RobotController
from .command_parser import CommandParser
from .config import MOTION_CONFIG
from .utils import get_local_ip
from .config import load_config, save_config
log = logging.getLogger(__name__)
api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/status', methods=['GET'])
def get_status_api():
    robot: RobotController = current_app.config['robot_controller']
    status_info = robot.get_status()
    if status_info:
        return jsonify({"status": "success", "robot_status": status_info})
    else:
        return jsonify({"status": "error", "message": "无法获取机器人状态。"}), 503

@api_bp.route('/server_info', methods=['GET'])
def get_server_info_api():
    return jsonify({
        "status": "success",
        "ip": get_local_ip(),
        "port": current_app.config.get('SERVER_PORT', 5000)
    })

@api_bp.route('/command', methods=['POST'])
def handle_command_api():
    robot: RobotController = current_app.config['robot_controller']
    parser: CommandParser = current_app.config['command_parser']
    
    data = request.get_json()
    command_text = data.get('commands', '').strip()
    if not command_text:
        return jsonify({"status": "error", "message": "指令不能为空。"}), 400

    log.info(f"收到指令批次:\n{command_text}")
    
    # --- 基础连接和模式设置 ---
    if not robot.connect():
        return jsonify({"status": "error", "message": "无法连接到机器人。"}), 503
    if not robot.set_auto_mode():
        return jsonify({"status": "error", "message": "无法切换机器人到自动模式。"}), 503

    # --- 阶段1 & 2: 双模解析 ---
    is_strict_format_batch = True
    strict_commands_list = []
    known_strict_prefixes = ["AUTO_MODE", "SET_SPEED", "MOVE", "GO_HOME", "PAUSE_MOVE", "CONTINUE_MOVE", "STOP_MOVE", "MONITOR", "TEST_WRITE_GV0"]

    for line in command_text.split('\n'):
        line = line.strip()
        if not line: continue
        
        normalized = parser.normalize_strict_command(line)
        if any(normalized.startswith(prefix) for prefix in known_strict_prefixes):
            strict_commands_list.append({'type': 'STRICT', 'line': line, 'normalized': normalized})
        else:
            is_strict_format_batch = False
            break # 只要有一行不符合，就整体用LLM

    commands_to_execute = []
    if is_strict_format_batch:
        log.info("所有指令均符合严格格式，按严格模式处理。")
        commands_to_execute = strict_commands_list
    else:
        log.info("检测到非严格格式指令，使用 LLM 解析整个批次。")
        llm_result = parser.parse_with_llm(command_text)
        if llm_result.get("error"):
            return jsonify({"status": "error", "message": f"LLM解析失败: {llm_result.get('message')}"}), 400
        commands_to_execute = llm_result.get("commands", [])

    # --- 阶段3: 执行指令序列 ---
    response_messages = []
    overall_status = "success"
    batch_motion_started = False

    for cmd_data in commands_to_execute:
        success = False
        motion_triggered = False
        original_line = cmd_data.get('line', command_text) # 对严格模式用行，对LLM用整个块
        
        try:
            # 根据指令来源（STRICT或LLM）进行分派
            if cmd_data.get('type') == 'STRICT':
                success, motion_triggered = execute_strict_command(robot, cmd_data['normalized'])
            else: # LLM parsed
                success, motion_triggered = execute_llm_command(robot, cmd_data)
        except Exception as e:
            log.error(f"执行指令 '{original_line}' 时发生内部异常: {e}", exc_info=True)
            success = False

        if motion_triggered:
            batch_motion_started = True
            if success: # 只有启动成功才等待
                log.info(f"等待运动完成 (来自: {original_line})...")
                success = robot.wait_for_motion_completion()
        
        msg_status = "success" if success else "error"
        response_messages.append({"command": original_line, "status": msg_status, "message": f"指令执行{'成功' if success else '失败'}。"})
        
        if not success:
            overall_status = "error"
            break # 一个失败，全部中断

    return jsonify({
        "status": overall_status,
        "message": "指令批次处理完成。" if overall_status == "success" else "指令批次处理中存在错误或中断。",
        "detailed_results": response_messages,
        "motion_started": batch_motion_started,
        "robot_status": robot.get_status()
    })

def execute_llm_command(robot: RobotController, cmd_data: dict) -> (bool, bool):
    """执行LLM解析出的单条指令，返回 (执行是否成功, 是否触发运动)"""
    cmd_type = cmd_data.get("command_type")
    params = cmd_data.get("parameters", {})
    
    if cmd_type == "SET_SPEED": return robot.set_speed(params.get("speed_value")), False
    if cmd_type == "MOVE_JOINT": return robot.start_incremental_move({params.get("axis_id"): params.get("angle")}, 'joint'), True
    if cmd_type == "MOVE_BASE": return robot.start_incremental_move({params.get("axis_name"): params.get("value")}, 'base_coords'), True
    if cmd_type == "GO_HOME_ALL": return robot.go_home(), True
    if cmd_type == "GO_HOME_JOINT": return robot.go_home(axis_id=params.get("axis_id")), True
    if cmd_type == "PAUSE_MOVE": return robot.pause_move(), False
    if cmd_type == "CONTINUE_MOVE": return robot.continue_move(), False
    if cmd_type == "STOP_MOVE": return robot.stop_move(), False
    if cmd_type == "MONITOR": return True, False
    if cmd_type == "TEST_WRITE_GV0": return robot.write_gv0_test(params.get("value")), False
        
    log.warning(f"接收到未知的LLM指令类型: {cmd_type}")
    return False, False

def execute_strict_command(robot: RobotController, normalized_cmd: str) -> (bool, bool):
    """执行严格格式的单条指令，返回 (执行是否成功, 是否触发运动)"""
    parts = normalized_cmd.split()
    cmd_type = parts[0]
    
    if cmd_type == "AUTO_MODE": return robot.set_auto_mode(), False
    if cmd_type == "SET_SPEED":
        speed = float(parts[1]) if len(parts) > 1 and parts[1] else MOTION_CONFIG.get('default_speed', 100.0)
        return robot.set_speed(speed), False
    if cmd_type == "MOVE":
        axis_part, value = parts[1], float(parts[2])
        if axis_part.startswith("J"):
            return robot.start_incremental_move({int(axis_part[1:]): value}, 'joint'), True
        else:
            return robot.start_incremental_move({axis_part: value}, 'base_coords'), True
    if cmd_type == "GO_HOME_ALL": return robot.go_home(), True
    if cmd_type == "GO_HOME_J": return robot.go_home(axis_id=int(parts[1])), True
    if cmd_type == "PAUSE_MOVE": return robot.pause_move(), False
    if cmd_type == "CONTINUE_MOVE": return robot.continue_move(), False
    if cmd_type == "STOP_MOVE": return robot.stop_move(), False
    if cmd_type == "MONITOR": return True, False
    if cmd_type == "TEST_WRITE_GV0": return robot.write_gv0_test(float(parts[1])), False
        
    log.warning(f"接收到未知的严格指令类型: {cmd_type}")
    return False, False

@api_bp.route('/settings', methods=['GET'])
def get_settings():
    """
    获取当前的配置信息。
    """
    log.info("请求获取当前配置...")
    try:
        current_config = load_config()
        # 出于安全考虑，可以在返回前移除敏感信息，例如API密钥
        # if 'llm_config' in current_config and 'api_key' in current_config['llm_config']:
        #     current_config['llm_config']['api_key'] = '********' 
        return jsonify({"status": "success", "settings": current_config})
    except Exception as e:
        log.error(f"读取配置文件失败: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "无法读取服务器配置。"}), 500

@api_bp.route('/settings', methods=['POST'])
def update_settings():
    """
    更新并保存配置信息。
    """
    log.info("收到配置更新请求...")
    new_settings = request.get_json()
    if not new_settings:
        return jsonify({"status": "error", "message": "请求体不能为空。"}), 400

    # 注意：不允许通过此API更改服务器端口，因为这需要重启
    server_port_before = load_config().get('server', {}).get('port')
    server_port_after = new_settings.get('server', {}).get('port')
    if server_port_before != server_port_after:
        log.warning("检测到服务器端口更改请求，此操作需要重启应用，将被忽略。")
        new_settings['server']['port'] = server_port_before

    success, error_msg = save_config(new_settings)
    if not success:
        return jsonify({"status": "error", "message": f"保存配置文件失败: {error_msg}"}), 500

    # 保存成功后，动态更新应用中的配置实例
    log.info("配置已保存，正在动态更新应用实例...")
    try:
        # 重新加载配置
        updated_config = load_config()
        robot_cfg = updated_config.get('robot', {})
        motion_cfg = updated_config.get('motion', {})
        llm_cfg = updated_config.get('llm_config', {})

        # 重新初始化控制器和解析器
        current_app.config['robot_controller'] = RobotController(robot_cfg, motion_cfg)
        current_app.config['command_parser'] = CommandParser(llm_cfg)
        
        log.info("RobotController 和 CommandParser 已使用新配置重新初始化。")
        return jsonify({"status": "success", "message": "配置已成功更新并应用。"})

    except Exception as e:
        log.critical(f"动态更新配置时发生严重错误: {e}", exc_info=True)
        return jsonify({
            "status": "error", 
            "message": "配置已保存，但动态应用新配置时发生错误。为确保所有更改生效，建议重启应用。"
        }), 500