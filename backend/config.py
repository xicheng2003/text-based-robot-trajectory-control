# backend/config.py (全新版本)

import json
import os
import sys
import logging
import shutil
from appdirs import user_data_dir

log = logging.getLogger(__name__)

# 定义您的应用信息，appdirs会用它来创建跨平台的路径
APP_NAME = "TextBasedRobotControl"
APP_AUTHOR = "Xicheng2003" 

# --- 关键函数：获取用户专属的配置文件路径 ---
def get_user_config_path():
    """获取用户数据目录下的配置文件路径，如果目录不存在则创建。"""
    data_dir = user_data_dir(APP_NAME, APP_AUTHOR)
    # 确保这个目录存在
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "config.json")

# --- 关键函数：获取打包资源（默认配置）的路径 ---
def get_bundled_resource_path(relative_path):
    """
    获取资源的正确路径, 无论是开发环境还是在PyInstaller打包的临时目录中。
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # 在打包后的环境中
        return os.path.join(sys._MEIPASS, relative_path)
    else:
        # 在开发环境中
        # 我们假设这个函数从 backend/config.py 被调用,
        # 所以默认配置文件在 'backend/default_config.json'
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(project_root, relative_path)

# --- 重写 load_config 函数 ---
def load_config():
    """
    加载用户专属的 config.json。如果不存在，则从打包的默认配置创建它。
    """
    user_config_file = get_user_config_path()
    log.info(f"正在从用户专属路径加载配置文件: {user_config_file}")

    if not os.path.exists(user_config_file):
        log.warning(f"用户配置文件不存在。将从默认配置创建新文件。")
        try:
            # default_config.json 在打包后会被放在 'backend' 目录下
            default_config_src = get_bundled_resource_path(os.path.join('backend', 'default_config.json'))
            shutil.copy(default_config_src, user_config_file)
            log.info(f"已成功创建新的用户配置文件。")
        except Exception as e:
            log.critical(f"无法创建用户配置文件: {e}", exc_info=True)
            sys.exit(1)

    try:
        with open(user_config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        log.critical(f"用户配置文件 '{user_config_file}' 格式错误: {e}。程序退出。")
        sys.exit(1)
    except Exception as e:
        log.critical(f"读取用户配置文件时发生未知错误: {e}", exc_info=True)
        sys.exit(1)


# --- 重写 save_config 函数 ---
def save_config(new_config_data):
    """
    将配置数据保存到用户专属的 config.json 文件中。
    """
    user_config_file = get_user_config_path()
    log.info(f"正在向用户专属路径写入配置文件: {user_config_file}")

    try:
        with open(user_config_file, 'w', encoding='utf-8') as f:
            json.dump(new_config_data, f, indent=2, ensure_ascii=False)
        return True, None
    except IOError as e:
        log.error(f"无法写入用户配置文件 '{user_config_file}': {e}")
        return False, str(e)


# --- 全局配置加载保持不变 ---
CONFIG = load_config()

ROBOT_CONFIG = CONFIG.get('robot', {})
MOTION_CONFIG = CONFIG.get('motion', {})
SERVER_CONFIG = CONFIG.get('server', {})
LLM_CONFIG = CONFIG.get('llm_config', {})