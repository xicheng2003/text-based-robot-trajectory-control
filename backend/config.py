# backend/config.py

import json
import os
import sys
import logging
from . import utils

log = logging.getLogger(__name__)

def load_config():
    """
    加载 config.json 文件。
    """
    project_root = utils.get_project_root()
    
    if utils.is_frozen():
        config_path = os.path.join(project_root, 'config.json')
    else:
        # 在开发模式下，config.json在backend目录
        config_path = os.path.join(project_root, 'backend', 'config.json')
        
    log.info(f"正在从以下路径加载配置文件: {config_path}")

    if not os.path.exists(config_path):
        log.critical(f"错误：配置文件 '{config_path}' 未找到。程序退出。")
        sys.exit(1)
        
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        log.critical(f"配置文件 '{config_path}' 格式错误: {e}。程序退出。")
        sys.exit(1)

# 加载配置并设为全局常量，供其他模块导入
CONFIG = load_config()

# 为方便使用，直接导出常用配置
ROBOT_CONFIG = CONFIG.get('robot', {})
MOTION_CONFIG = CONFIG.get('motion', {})
SERVER_CONFIG = CONFIG.get('server', {})
LLM_CONFIG = CONFIG.get('llm_config', {})