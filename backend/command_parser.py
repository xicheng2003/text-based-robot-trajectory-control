# backend/command_parser.py

import re
import json
import logging
from openai import OpenAI, APIStatusError, APIConnectionError, APITimeoutError
from typing import Dict, Any, List

log = logging.getLogger(__name__)

# LLM Prompt保持不变，内容很长，这里用注释代替
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

class CommandParser:
    def __init__(self, llm_config: Dict[str, Any]):
        self.llm_client = None
        self.llm_model_name = llm_config.get('model_name')
        if llm_config.get('api_key'):
            try:
                self.llm_client = OpenAI(
                    api_key=llm_config['api_key'], 
                    base_url=llm_config.get('api_base_url')
                )
                log.info("LLM 客户端初始化成功。")
            except Exception as e:
                log.error(f"LLM 客户端初始化失败: {e}")
        else:
            log.warning("未配置 LLM API Key，自然语言控制不可用。")

    def normalize_strict_command(self, command_text: str) -> str:
        """
        尝试将中文指令或其组合规范化为标准的英文指令格式。
        """
        command_text_upper = command_text.strip().upper()

        if command_text_upper in ["AUTO_MODE", "自动模式"]: return "AUTO_MODE"
        if command_text_upper in ["PAUSE_MOVE", "暂停运动"]: return "PAUSE_MOVE"
        if command_text_upper in ["CONTINUE_MOVE", "继续运动"]: return "CONTINUE_MOVE"
        if command_text_upper in ["STOP_MOVE", "停止运动"]: return "STOP_MOVE"
        if command_text_upper in ["GO_HOME_ALL", "全轴回零"]: return "GO_HOME_ALL"
        if command_text_upper in ["MONITOR", "状态监控"]: return "MONITOR"

        match_speed = re.match(r"^(SET_SPEED|设置速度)\s*([\d\.\-]+)?$", command_text_upper)
        if match_speed:
            return f"SET_SPEED {match_speed.group(2) or ''}".strip()

        match_test_gv0 = re.match(r"^(TEST_WRITE_GV0|测试写入GV0)\s+([\d\.\-]+)$", command_text_upper)
        if match_test_gv0:
            return f"TEST_WRITE_GV0 {match_test_gv0.group(2)}"

        match_move_joint = re.match(r"^(MOVE|移动)\s+J(\d+)\s+([\d\.\-]+)$", command_text_upper)
        if match_move_joint:
            return f"MOVE J{match_move_joint.group(2)} {match_move_joint.group(3)}"

        match_move_base = re.match(r"^(MOVE|移动)\s+([XYZABC])\s+([\d\.\-]+)$", command_text_upper)
        if match_move_base:
            return f"MOVE {match_move_base.group(2)} {match_move_base.group(3)}"
    
        match_home_joint = re.match(r"^(GO_HOME_J|回零 J)(\d+)$", command_text_upper)
        if match_home_joint:
            # 注意：原始代码返回 GO_HOME_J<id>，但为了解析方便，返回 GO_HOME_J <id> 更好
            return f"GO_HOME_J {match_home_joint.group(2)}"

        return command_text_upper # 返回原始大写文本以示未知

    def parse_with_llm(self, user_query: str) -> Dict[str, Any]:
        """使用LLM解析自然语言指令。"""
        if not self.llm_client:
            return {"commands": [], "error": "LLM_NOT_CONFIGURED", "message": "LLM服务未配置。"}
        if not self.llm_model_name:
            return {"commands": [], "error": "LLM_MODEL_NOT_CONFIGURED", "message": "LLM模型名称未配置。"}

        messages = [{"role": "system", "content": LLM_SYSTEM_PROMPT}, {"role": "user", "content": user_query}]
        
        try:
            log.info(f"调用 LLM API 解析: '{user_query[:50]}...'")
            chat_completion = self.llm_client.chat.completions.create(
                model=self.llm_model_name,
                messages=messages,
                response_format={"type": "json_object"}
            )
            response_content = chat_completion.choices[0].message.content
            parsed_output = json.loads(response_content)
            if "commands" not in parsed_output or not isinstance(parsed_output["commands"], list):
                raise ValueError("LLM返回的JSON结构不符合预期")
            return parsed_output
        except (APIStatusError, APIConnectionError, APITimeoutError) as e:
            msg = f"LLM服务连接失败或返回错误: {e.status_code if hasattr(e, 'status_code') else str(e)}"
            log.error(msg)
            return {"commands": [], "error": "LLM_API_ERROR", "message": msg}
        except (json.JSONDecodeError, ValueError) as e:
            log.error(f"LLM 返回的不是有效或预期的JSON。错误: {e}. 响应: {response_content}")
            return {"commands": [], "error": "LLM_INVALID_JSON", "message": "LLM未能返回有效或预期的JSON。"}
        except Exception as e:
            log.error(f"LLM解析过程中发生未知异常: {e}", exc_info=True)
            return {"commands": [], "error": "LLM_UNKNOWN_ERROR", "message": f"LLM解析时发生未知错误: {e}"}