import sys
import time
import os
import socket
import json
import keyboard
import cv2
import mediapipe as mp
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QThread, Signal, QPointF, QTimer
from PySide6.QtGui import QPainter, QColor, QPen

# 导入配置和滤波器
import config
from one_euro_filter import PoseFilterManager

# 加载配置
APP_CONFIG = config.load_config()


class ConfigWatcher(QThread):
    # 配置文件热重载监控器
    sig_config_reloaded = Signal(dict)

    def __init__(self, config_file="config.json", interval_ms=1000):
        super().__init__()
        self.config_file = config_file
        self.interval_ms = interval_ms
        self._is_running = True
        self._last_mtime = 0
        if os.path.exists(self.config_file):
            self._last_mtime = os.path.getmtime(self.config_file)

    def update_config(self, new_config: dict):
        """接收到配置热重载信号后更新内部参数"""
        global APP_CONFIG
        APP_CONFIG = new_config
        min_c = new_config.get("min_cutoff", 0.5)
        beta = new_config.get("beta", 0.01)
        d_c = new_config.get("d_cutoff", 1.0)

        for f in [
            self.ui_pose_filter,
            self.ui_face_filter,
            self.ui_lh_filter,
            self.ui_rh_filter,
            self.world_pose_filter,
            self.world_face_filter,
            self.world_lh_filter,
            self.world_rh_filter,
        ]:
            f.update_params(min_c, beta, d_c)

        print(
            f"[Vision] Holistic Filter params updated: min_cutoff={min_c}, beta={beta}"
        )

        if udp_provider:
            ip = new_config.get("udp_ip", "127.0.0.1")
            port = new_config.get("udp_port", 7001)
            udp_provider.update_address(ip, port)

    def _process_landmarks(self, landmarks, filter_manager, is_world=False):
        import time

        if not landmarks:
            return []
        current_t = time.time()
        raw_points = []
        visibility_list = []

        for lm in landmarks.landmark:
            if is_world:
                raw_points.append((lm.x, lm.y, lm.z))
                visibility_list.append(getattr(lm, "visibility", 1.0))
            else:
                raw_points.append((lm.x, lm.y, getattr(lm, "z", 0.0)))

        smoothed = filter_manager.process(raw_points, current_t)

        if is_world:
            flip_x = APP_CONFIG.get("flip_x", False)
            flip_y = APP_CONFIG.get("flip_y", False)
            flip_z = APP_CONFIG.get("flip_z", False)
            res = []
            for i, (x_hat, y_hat, z_hat) in enumerate(smoothed):
                res.append(
                    {
                        "id": i,
                        "x": -x_hat if flip_x else x_hat,
                        "y": -y_hat if flip_y else y_hat,
                        "z": -z_hat if flip_z else z_hat,
                        "visibility": visibility_list[i],
                    }
                )
            return res
        else:
            res = []
            for x_hat, y_hat, _ in smoothed:
                res.append(
                    QPointF(x_hat * self.screen_width, y_hat * self.screen_height)
                )
            return res

    def run(self):
        import time

        cap = cv2.VideoCapture(self.camera_index)

        with self.mp_holistic.Holistic(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=False,
            enable_segmentation=False,
            refine_face_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        ) as holistic:
            while self._is_running and cap.isOpened():
                success, image = cap.read()
                if not success:
                    time.sleep(0.01)
                    continue

                image.flags.writeable = False
                image = cv2.cvtColor(cv2.flip(image, 1), cv2.COLOR_BGR2RGB)

                results = holistic.process(image)

                ui_data = {"pose": [], "face": [], "left_hand": [], "right_hand": []}
                world_data = {"pose": [], "face": [], "left_hand": [], "right_hand": []}
                has_data = False

                if results.pose_landmarks:
                    has_data = True
                    ui_data["pose"] = self._process_landmarks(
                        results.pose_landmarks, self.ui_pose_filter, is_world=False
                    )
                    if results.pose_world_landmarks:
                        world_data["pose"] = self._process_landmarks(
                            results.pose_world_landmarks,
                            self.world_pose_filter,
                            is_world=True,
                        )
                else:
                    self.ui_pose_filter.reset()
                    self.world_pose_filter.reset()

                if results.face_landmarks:
                    ui_data["face"] = self._process_landmarks(
                        results.face_landmarks, self.ui_face_filter, is_world=False
                    )
                    world_data["face"] = self._process_landmarks(
                        results.face_landmarks, self.world_face_filter, is_world=True
                    )
                else:
                    self.ui_face_filter.reset()
                    self.world_face_filter.reset()

                if results.left_hand_landmarks:
                    ui_data["left_hand"] = self._process_landmarks(
                        results.left_hand_landmarks, self.ui_lh_filter, is_world=False
                    )
                    world_data["left_hand"] = self._process_landmarks(
                        results.left_hand_landmarks, self.world_lh_filter, is_world=True
                    )
                else:
                    self.ui_lh_filter.reset()
                    self.world_lh_filter.reset()

                if results.right_hand_landmarks:
                    ui_data["right_hand"] = self._process_landmarks(
                        results.right_hand_landmarks, self.ui_rh_filter, is_world=False
                    )
                    world_data["right_hand"] = self._process_landmarks(
                        results.right_hand_landmarks,
                        self.world_rh_filter,
                        is_world=True,
                    )
                else:
                    self.ui_rh_filter.reset()
                    self.world_rh_filter.reset()

                if has_data:
                    self.sig_pose_data_updated.emit(ui_data)
                    self.sig_3d_data_ready.emit(world_data)
                else:
                    self.sig_pose_data_updated.emit({})

        cap.release()

    def stop(self):
        self._is_running = False
        self.wait()


class TransparentOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.pose_data = {}  # 保存最新接收到的 Holistic 字典

        # 实时参数显示状态
        self.current_config = APP_CONFIG.copy()
        self.heartbeat_visible = False
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(self._toggle_heartbeat)
        self.heartbeat_timer.start(100)  # 每 100ms 闪烁一次

        self.initUI()

    def _toggle_heartbeat(self):
        self.heartbeat_visible = not self.heartbeat_visible
        self.update()

    def update_config_ui(self, new_config):
        """当 ConfigWatcher 检测到配置更改时，更新 UI 面板"""
        self.current_config = new_config.copy()
        self.update()

    def heartbeat(self):
        """接收到 UDP 发送心跳"""
        # 这里可以通过计数器或重置计时器来实现更精细的闪烁逻辑，目前用定时器自动闪烁代替
        pass

    def initUI(self):
        # Window flags: Frameless, Always on Top, Click-through, Tool
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.Tool
        )

        # Make background transparent
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Full screen on primary monitor
        screen = QApplication.primaryScreen()
        geometry = screen.geometry()
        self.setGeometry(geometry)

    def update_pose_data(self, data_dict: dict):
        """Slot to receive new pose data and trigger a repaint."""
        self.pose_data = data_dict
        self.update()  # Schedule a paintEvent

    def toggle_visibility(self):
        """Slot to handle visibility toggle from the global hotkey."""
        if self.isVisible():
            self.hide()
        else:
            self.show()

    def exit_application(self):
        """Slot to cleanly exit the application."""
        print("Exiting application...")
        QApplication.quit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Static border drawing (to verify transparency bounds)
        pen_border = QPen(QColor(255, 0, 0, 100))
        pen_border.setWidth(10)
        painter.setPen(pen_border)
        painter.drawRect(5, 5, self.width() - 10, self.height() - 10)

        # --- Draw HUD Panel ---
        # Draw semi-transparent background for HUD
        painter.setBrush(QColor(0, 0, 0, 150))
        painter.setPen(Qt.PenStyle.NoPen)
        hud_rect = self.rect().adjusted(
            20, 20, -self.width() + 320, -self.height() + 180
        )
        painter.drawRoundedRect(hud_rect, 10, 10)

        # Draw text info
        painter.setPen(QColor(255, 255, 255, 255))
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)

        # 绘制状态灯
        if self.current_config.get("udp_enabled", True):
            if self.heartbeat_visible:
                painter.setBrush(QColor(0, 255, 0, 255))  # Green Blink
            else:
                painter.setBrush(QColor(0, 100, 0, 255))  # Dark Green
            status_text = "UDP: 发送中"
        else:
            painter.setBrush(QColor(255, 0, 0, 255))  # Red Off
            status_text = "UDP: 已停用"

        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(30, 35, 12, 12)

        painter.setPen(QColor(255, 255, 255, 255))
        painter.drawText(50, 45, status_text)

        # 绘制参数
        y_offset = 70
        painter.drawText(
            30,
            y_offset,
            f"目标: {self.current_config.get('udp_ip')}:{self.current_config.get('udp_port')}",
        )
        y_offset += 25
        painter.drawText(
            30, y_offset, f"1€ min_cutoff: {self.current_config.get('min_cutoff')}"
        )
        y_offset += 25
        painter.drawText(30, y_offset, f"1€ beta: {self.current_config.get('beta')}")
        y_offset += 25

        flip_x = self.current_config.get("flip_x", False)
        flip_y = self.current_config.get("flip_y", False)
        flip_z = self.current_config.get("flip_z", False)
        painter.drawText(30, y_offset, f"翻转: X({flip_x}) Y({flip_y}) Z({flip_z})")

        # --- End HUD Panel ---

        # --- Draw Holistic Skeleton ---
        if not self.pose_data:
            return

        face_pts = self.pose_data.get("face", [])
        if face_pts:
            painter.setPen(QColor(255, 255, 255, 80))
            for pt in face_pts:
                painter.drawPoint(pt)

        pose_pts = self.pose_data.get("pose", [])
        if pose_pts and len(pose_pts) == 33:
            pen_bone = QPen(QColor(0, 255, 255, 180))
            pen_bone.setWidth(4)
            painter.setPen(pen_bone)
            for connection in mp.solutions.holistic.POSE_CONNECTIONS:
                pt1 = pose_pts[connection[0]]
                pt2 = pose_pts[connection[1]]
                painter.drawLine(pt1, pt2)

            painter.setBrush(QColor(255, 0, 0, 200))
            painter.setPen(Qt.PenStyle.NoPen)
            for pt in pose_pts:
                painter.drawEllipse(pt, 6, 6)

            painter.setBrush(QColor(255, 255, 0, 150))
            painter.drawEllipse(pose_pts[0], 20, 20)

        def draw_hand(hand_pts, hand_color):
            if not hand_pts or len(hand_pts) != 21:
                return
            pen_hand = QPen(hand_color)
            pen_hand.setWidth(3)
            painter.setPen(pen_hand)
            for connection in mp.solutions.holistic.HAND_CONNECTIONS:
                pt1 = hand_pts[connection[0]]
                pt2 = hand_pts[connection[1]]
                painter.drawLine(pt1, pt2)
            painter.setBrush(hand_color)
            painter.setPen(Qt.PenStyle.NoPen)
            for pt in hand_pts:
                painter.drawEllipse(pt, 4, 4)

        draw_hand(self.pose_data.get("left_hand", []), QColor(0, 255, 0, 200))
        draw_hand(self.pose_data.get("right_hand", []), QColor(255, 165, 0, 200))


class UdpSender(QThread):
    # 发射心跳信号，告诉 UI 成功发送了一帧数据
    sig_heartbeat = Signal()

    def __init__(self, ip, port):
        super().__init__()
        self.ip = ip
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)

    def send(self, data_list):
        try:
            # 包装为字典，方便 Unity 的 JsonUtility 反序列化 (不支持直接反序列化顶级数组)
            payload = {"landmarks": data_list}
            msg = json.dumps(payload, separators=(",", ":"))
            self.sock.sendto(msg.encode("utf-8"), (self.ip, self.port))
            # 发射心跳
            self.sig_heartbeat.emit()
        except BlockingIOError:
            pass
        except Exception as e:
            print(f"[UDP] 发送错误: {e}")

    def update_address(self, ip, port):
        self.ip = ip
        self.port = port

    def close(self):
        self.sock.close()


# 全局 UDP 实例
udp_provider = UdpSender(
    APP_CONFIG.get("udp_ip", "127.0.0.1"), APP_CONFIG.get("udp_port", 7001)
)


def on_3d_data_ready(data):
    if APP_CONFIG.get("udp_enabled", True):
        udp_provider.send(data)
    # 此处为测试打印，为了防止控制台被刷屏，我们仅在特定的帧（比如每10帧）或调试模式下输出
    # print(json.dumps(data[:3], indent=2))  # 测试只打印前三个关节点 (通常是鼻子和眼睛)
    pass


if __name__ == "__main__":
    app = QApplication(sys.argv)

    overlay = TransparentOverlay()

    # Setup Global Hotkeys
    hotkey_thread = GlobalHotkeyManager()
    hotkey_thread.sig_toggle_visibility.connect(overlay.toggle_visibility)
    hotkey_thread.sig_exit_app.connect(overlay.exit_application)
    hotkey_thread.start()

    # Setup Computer Vision Tracking (OpenCV + MediaPipe Pose)
    vision_thread = VisionCaptureThread(
        overlay.width(), overlay.height(), camera_index=0
    )
    vision_thread.sig_pose_data_updated.connect(overlay.update_pose_data)

    # 连接 3D 真实世界坐标数据流
    vision_thread.sig_3d_data_ready.connect(on_3d_data_ready)

    # 接收发送心跳供 UI 刷新 (由于 UdpSender 改为 QThread，我们需要确保它是主线程可用的实例)
    # 因为我们在 on_3d_data_ready 里调用全局的 udp_provider 实例，所以我们可以在主程序的初始化处链接心跳信号
    udp_provider.sig_heartbeat.connect(overlay.heartbeat)

    # Setup Config Watcher (热重载配置文件)
    watcher_thread = ConfigWatcher()
    watcher_thread.sig_config_reloaded.connect(vision_thread.update_config)
    watcher_thread.sig_config_reloaded.connect(overlay.update_config_ui)
    watcher_thread.start()

    vision_thread.start()

    # Show the canvas
    overlay.show()

    # Execute application
    exit_code = app.exec()

    # Clean up threads
    watcher_thread.stop()
    vision_thread.stop()
    hotkey_thread.stop()

    if udp_provider:
        udp_provider.close()

    sys.exit(exit_code)
