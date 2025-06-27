# backend/app.py

import os
import logging
import threading
import webbrowser
from flask import Flask, send_from_directory
from . import utils
from .config import SERVER_CONFIG, ROBOT_CONFIG, MOTION_CONFIG, LLM_CONFIG
from .robot_controller import RobotController
from .command_parser import CommandParser
from .routes import api_bp

# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(module)s] %(message)s')
log = logging.getLogger(__name__)

# --- 创建应用实例 ---
def create_app():
    project_root = utils.get_project_root()
    static_dir = os.path.join(project_root, 'frontend', 'dist')
    
    # 检查静态文件目录是否存在
    if not os.path.exists(static_dir):
        log.warning(f"前端静态文件目录 '{static_dir}' 不存在。请先运行 'npm run build'。")
        # 在这种情况下，可以只提供API服务，或者优雅地退出
        # 这里我们选择继续运行，但Web界面将无法访问
    
    log.info(f"Flask 静态文件目录设置为: {static_dir}")
    app = Flask(__name__, static_folder=static_dir)

    # 将配置注入到app.config中，方便路由访问
    app.config['robot_controller'] = RobotController(ROBOT_CONFIG, MOTION_CONFIG)
    app.config['command_parser'] = CommandParser(LLM_CONFIG)
    app.config['SERVER_PORT'] = SERVER_CONFIG.get('port', 5000)

    # 注册API蓝图
    app.register_blueprint(api_bp)

    # --- Vue前端服务路由 ---
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def serve_vue_app(path):
        if not app.static_folder or not os.path.exists(app.static_folder):
             return "前端文件未找到。请确保 'frontend/dist' 目录存在。", 404

        if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
            return send_from_directory(app.static_folder, path)
        else:
            index_path = os.path.join(app.static_folder, 'index.html')
            if not os.path.exists(index_path):
                return "应用入口 index.html 未找到。", 404
            return send_from_directory(app.static_folder, 'index.html')

    return app

# --- 启动逻辑 ---
def open_browser(port):
    """自动打开浏览器"""
    webbrowser.open_new_tab(f"http://127.0.0.1:{port}")

if __name__ == '__main__':
    app = create_app()
    host = SERVER_CONFIG.get('host', '0.0.0.0')
    port = app.config['SERVER_PORT']
    
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        threading.Timer(1.25, open_browser, args=[port]).start()
    
    log.info(f"服务器将在 http://{host}:{port} 上启动...")
    app.run(host=host, port=port, debug=False)