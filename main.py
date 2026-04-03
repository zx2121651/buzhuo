import sys
from PySide6.QtWidgets import QApplication

# 导入拆分后的子模块
from modules import config
from modules.hotkeys import GlobalHotkeyManager
from modules.config_watcher import ConfigWatcher
from modules.udp_sender import UdpSender
from modules.ui_overlay import TransparentOverlay
from modules.vision_capture import VisionCaptureThread


def on_3d_data_ready(data):
    """
    接收来自 VisionCaptureThread 的 3D 数据，并触发 UDP 发送
    """
    if APP_CONFIG.get("udp_enabled", True):
        udp_provider.send(data)
    # Debug: print(json.dumps(data.get("pose", [])[:1], indent=2))


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # 加载初始配置
    APP_CONFIG = config.load_config()

    # 初始化 UDP 异步发送服务
    udp_provider = UdpSender(
        APP_CONFIG.get("udp_ip", "127.0.0.1"), APP_CONFIG.get("udp_port", 7001)
    )

    # 初始化 UI 全屏透明面板
    overlay = TransparentOverlay(APP_CONFIG)

    # 初始化并连接全键盘监听服务
    hotkey_thread = GlobalHotkeyManager()
    hotkey_thread.sig_toggle_visibility.connect(overlay.toggle_visibility)
    hotkey_thread.sig_exit_app.connect(overlay.exit_application)
    hotkey_thread.start()

    # 初始化并连接核心捕获与解算线程
    vision_thread = VisionCaptureThread(overlay.width(), overlay.height(), APP_CONFIG)
    # 连接 2D 绘图数据流到 UI
    vision_thread.sig_pose_data_updated.connect(overlay.update_pose_data)
    # 连接 3D 世界数据流到 发送端
    vision_thread.sig_3d_data_ready.connect(on_3d_data_ready)

    # 将 UDP 的成功发送心跳反馈给 UI 指示灯
    udp_provider.sig_heartbeat.connect(overlay.heartbeat)

    # 初始化并连接配置热重载服务
    watcher_thread = ConfigWatcher()
    watcher_thread.sig_config_reloaded.connect(vision_thread.update_config)
    watcher_thread.sig_config_reloaded.connect(overlay.update_config_ui)

    # [新增] 连接 UDP 热重载
    def update_udp_address(new_config):
        ip = new_config.get("udp_ip", "127.0.0.1")
        port = new_config.get("udp_port", 7001)
        udp_provider.update_address(ip, port)
        global APP_CONFIG
        APP_CONFIG = new_config

    watcher_thread.sig_config_reloaded.connect(update_udp_address)
    watcher_thread.start()

    # 启动核心捕捉线程并显示 UI
    vision_thread.start()
    overlay.show()

    # 进入 Qt 主事件循环
    exit_code = app.exec()

    # 安全地清理所有后台线程
    print("[System] Shutting down services...")
    watcher_thread.stop()
    vision_thread.stop()
    hotkey_thread.stop()
    udp_provider.close()

    sys.exit(exit_code)
