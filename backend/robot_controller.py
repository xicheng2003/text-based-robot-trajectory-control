# backend/robot_controller.py

import logging
import time
from typing import Dict, Any, Optional, List
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException
from . import utils

log = logging.getLogger(__name__)

class RobotController:
    """封装与机器人通过Modbus TCP的所有交互。"""
    def __init__(self, robot_config: Dict, motion_config: Dict):
        self.host = robot_config.get('ip')
        self.port = robot_config.get('port', 502)
        self.slave_id = robot_config.get('slave_id', 1)
        self.client: Optional[ModbusTcpClient] = None
        self.current_speed_setting = float(motion_config.get('default_speed', 100.0))

    def connect(self) -> bool:
        if self.client and self.client.is_socket_open():
            return True
        log.info(f"尝试连接到机器人 Modbus TCP 从站 {self.host}:{self.port}...")
        try:
            # 设置合理的超时时间
            self.client = ModbusTcpClient(host=self.host, port=self.port, timeout=3)
            if self.client.connect():
                log.info(f"成功连接到机器人，Unit ID: {self.slave_id}。")
                return True
            else:
                self.client = None
                log.error("Modbus连接失败。")
                return False
        except Exception as e:
            self.client = None
            log.error(f"连接过程中发生未知错误: {e}", exc_info=True)
            return False

    def _execute_read(self, address, count, op_name) -> Optional[List[int]]:
        try:
            result = self.client.read_holding_registers(address=address, count=count, slave=self.slave_id)
            if utils.is_modbus_response_ok(result):
                return result.registers
            log.error(f"{op_name} 失败. Modbus响应: {result}")
            return None
        except (ModbusException, ConnectionRefusedError) as e:
            log.error(f"{op_name} Modbus异常: {e}")
            self.client.close() # 连接出问题，关闭它
            return None

    def _execute_write(self, address, values, op_name) -> bool:
        try:
            if isinstance(values, list):
                result = self.client.write_registers(address, values, slave=self.slave_id)
            else:
                result = self.client.write_register(address, values, slave=self.slave_id)
            
            if not utils.is_modbus_response_ok(result):
                log.error(f"{op_name} 失败. Modbus响应: {result}")
                return False
            return True
        except (ModbusException, ConnectionRefusedError) as e:
            log.error(f"{op_name} Modbus异常: {e}")
            self.client.close()
            return False

    # --- 高层API ---
    def set_auto_mode(self) -> bool:
        return self._execute_write(444, 1, "切换自动模式")

    def set_speed(self, speed: float) -> bool:
        self.current_speed_setting = float(speed)
        registers = utils.float_to_modbus_registers(self.current_speed_setting)
        return self._execute_write(450, registers, f"设置速度为 {speed}")

    def start_incremental_move(self, offsets: Dict, coordinate_type: str) -> bool:
        # 确保速度已设置
        self.set_speed(self.current_speed_setting)
        
        all_offsets = [0.0] * 6
        axis_map = {'X': 0, 'Y': 1, 'Z': 2, 'A': 3, 'B': 4, 'C': 5}
        for key, value in offsets.items():
            if isinstance(key, int) and 1 <= key <= 6:
                all_offsets[key - 1] = float(value)
            elif isinstance(key, str) and key.upper() in axis_map:
                all_offsets[axis_map[key.upper()]] = float(value)
        
        registers = [reg for val in all_offsets for reg in utils.float_to_modbus_registers(val)]
        if not self._execute_write(400, registers, "设置增量运动偏移量"):
            return False

        move_code = 0x40 if coordinate_type == 'joint' else 0x41
        return self._execute_write(440, move_code, f"启动{coordinate_type}增量运动")

    def go_home(self, axis_id: Optional[int] = None) -> bool:
        if axis_id:
            if not (1 <= axis_id <= 6):
                log.error(f"无效的轴号: {axis_id}"); return False
            value, op_name = axis_id - 1, f"执行J{axis_id}回零"
        else:
            value, op_name = 0x0B, "执行全轴回零"
        return self._execute_write(445, value, op_name)

    def pause_move(self) -> bool: return self._execute_write(442, 0x01, "暂停运动")
    def continue_move(self) -> bool: return self._execute_write(443, 0x01, "继续运动")
    def stop_move(self) -> bool: return self._execute_write(441, 0x01, "停止运动")
    def write_gv0_test(self, value: float) -> bool:
        registers = utils.float_to_modbus_registers(float(value))
        return self._execute_write(0, registers, f"写入GV0测试值 {value}")

    def get_status(self) -> Optional[Dict[str, Any]]:
        if not self.connect(): return None
        
        # 批量读取以提高效率
        status_regs = self._execute_read(560, 3, "读取状态寄存器")
        gv0_regs = self._execute_read(0, 2, "读取GV0")

        if status_regs is None: return None # 读取失败

        status_data = {"mode": "未知", "run_status": "未知", "alarm_status": "无报警", "alarm_code": 0, "gv0_value": None}
        
        mode_map = {0: "手动模式", 1: "自动模式", 2: "Modbus示教使能"}
        status_data["mode"] = mode_map.get(status_regs[0], f"未知({status_regs[0]})")
        
        run_map = {0: "停止", 1: "正在运行", 2: "暂停"}
        status_data["run_status"] = run_map.get(status_regs[1], f"未知({status_regs[1]})")

        alarm_code = status_regs[2]
        status_data["alarm_code"] = alarm_code
        if alarm_code != 0:
            desc = []
            if alarm_code & 1: desc.append("急停报警")
            if alarm_code & 2: desc.append("伺服报警")
            if alarm_code & 4: desc.append("刹车异常")
            if alarm_code & 8: desc.append("算法报警")
            if alarm_code & 16: desc.append("编码器角度报警")
            status_data["alarm_status"] = f"有报警 ({hex(alarm_code)}): " + ", ".join(desc)
        
        if gv0_regs:
            status_data["gv0_value"] = utils.modbus_registers_to_float(gv0_regs)
            
        return status_data

    def wait_for_motion_completion(self, timeout=30, poll_interval=0.5) -> bool:
        log.info(f"等待运动完成 (最长 {timeout}s)...")
        start_time = time.time()
        
        # 等待进入“运行中”
        for _ in range(int(5 / poll_interval)):
            status = self.get_status()
            if not status or status["alarm_code"] != 0:
                log.error(f"运动启动前或过程中检测到报警: {status.get('alarm_status', '未知') if status else '无法获取状态'}")
                return False
            if status["run_status"] == "正在运行": break
            time.sleep(poll_interval)
        else:
            log.warning("机器人未在5秒内进入'运行中'状态，运动可能未启动。")
            return False

        # 等待返回“停止”
        while time.time() - start_time < timeout:
            status = self.get_status()
            if not status or status["alarm_code"] != 0:
                log.error(f"运动过程中检测到报警: {status.get('alarm_status', '未知') if status else '无法获取状态'}")
                return False
            if status["run_status"] == "停止":
                log.info("运动完成。")
                return True
            time.sleep(poll_interval)
            
        log.warning(f"运动超时 ({timeout}s)。")
        return False