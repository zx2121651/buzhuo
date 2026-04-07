import mediapipe as mp
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor, QPen


class TransparentOverlay(QWidget):
    """
    基于 PySide6 的透明全屏画布与控制台面板
    """

    def __init__(self, initial_config):
        super().__init__()
        self.pose_data = {}  # 保存最新接收到的 Holistic 字典
        self.current_config = initial_config.copy()

        # 心跳闪烁状态
        self.heartbeat_visible = False
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(self._toggle_heartbeat)
        self.heartbeat_timer.start(100)  # 每 100ms 闪烁一次

        self.initUI()

    def _toggle_heartbeat(self):
        self.heartbeat_visible = not self.heartbeat_visible
        self.update()

    def initUI(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        screen = QApplication.primaryScreen()
        geometry = screen.geometry()
        self.setGeometry(geometry)

    def update_config_ui(self, new_config):
        self.current_config = new_config.copy()
        self.update()

    def update_pose_data(self, data_dict: dict):
        self.pose_data = data_dict
        self.update()

    def heartbeat(self):
        # 接收到 UDP 心跳信号（由于是用 timer 闪烁，此槽暂保留为空）
        pass

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()

    def exit_application(self):
        print("Exiting application...")
        QApplication.quit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 边界验证框
        pen_border = QPen(QColor(255, 0, 0, 100))
        pen_border.setWidth(10)
        painter.setPen(pen_border)
        painter.drawRect(5, 5, self.width() - 10, self.height() - 10)

        # --- Draw HUD Panel ---
        painter.setBrush(QColor(0, 0, 0, 150))
        painter.setPen(Qt.PenStyle.NoPen)
        hud_rect = self.rect().adjusted(
            20, 20, -self.width() + 350, -self.height() + 200
        )
        painter.drawRoundedRect(hud_rect, 10, 10)

        painter.setPen(QColor(255, 255, 255, 255))
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)

        if self.current_config.get("udp_enabled", True):
            if self.heartbeat_visible:
                painter.setBrush(QColor(0, 255, 0, 255))
            else:
                painter.setBrush(QColor(0, 100, 0, 255))
            status_text = "UDP: 发送中"
        else:
            painter.setBrush(QColor(255, 0, 0, 255))
            status_text = "UDP: 已停用"

        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(30, 35, 12, 12)

        painter.setPen(QColor(255, 255, 255, 255))
        painter.drawText(50, 45, status_text)

        y_offset = 70
        input_mode_str = self.current_config.get("input_mode", "camera").upper()
        if input_mode_str == "VIDEO":
            vid_path = self.current_config.get("video_path", "")
            if len(vid_path) > 15:
                vid_path = "..." + vid_path[-12:]
            input_mode_str += f" ({vid_path})"
        painter.drawText(30, y_offset, f"源头: {input_mode_str}")

        y_offset += 25
        painter.drawText(
            30,
            y_offset,
            f"目标: {self.current_config.get('udp_ip')}:{self.current_config.get('udp_port')}",
        )

        y_offset += 25
        painter.drawText(
            30,
            y_offset,
            f"1€ Filter: min({self.current_config.get('min_cutoff')}) beta({self.current_config.get('beta')})",
        )

        y_offset += 25
        flip_x = self.current_config.get("flip_x", False)
        flip_y = self.current_config.get("flip_y", False)
        flip_z = self.current_config.get("flip_z", False)
        painter.drawText(30, y_offset, f"翻转: X({flip_x}) Y({flip_y}) Z({flip_z})")

        y_offset += 25
        enable_depth = self.current_config.get("enable_global_depth", True)
        if enable_depth:
            ref_w = self.current_config.get("ref_shoulder_width_m", 0.40)
            focal = self.current_config.get("camera_focal_length_px", 800)
            painter.drawText(
                30, y_offset, f"绝对深度(Global Z): 开启 [Ref:{ref_w}m, Focal:{focal}]"
            )
        else:
            painter.setPen(QColor(255, 100, 100))
            painter.drawText(30, y_offset, f"绝对深度(Global Z): 关闭 (原地踏步)")
            painter.setPen(QColor(255, 255, 255))
        # --- End HUD Panel ---

        if not self.pose_data:
            return

        # 1. 脸部
        face_pts = self.pose_data.get("face", [])
        if face_pts:
            painter.setPen(QColor(255, 255, 255, 80))
            for pt in face_pts:
                painter.drawPoint(pt)

        # 2. 身体
        pose_pts = self.pose_data.get("pose", [])
        if pose_pts and len(pose_pts) == 33:
            pen_bone = QPen(QColor(0, 255, 255, 180))
            pen_bone.setWidth(4)
            painter.setPen(pen_bone)
            for connection in mp.solutions.holistic.POSE_CONNECTIONS:
                painter.drawLine(pose_pts[connection[0]], pose_pts[connection[1]])

            painter.setBrush(QColor(255, 0, 0, 200))
            painter.setPen(Qt.PenStyle.NoPen)
            for pt in pose_pts:
                painter.drawEllipse(pt, 6, 6)

            painter.setBrush(QColor(255, 255, 0, 150))
            painter.drawEllipse(pose_pts[0], 20, 20)

        # 3. 双手
        def draw_hand(hand_pts, hand_color):
            if not hand_pts or len(hand_pts) != 21:
                return
            pen_hand = QPen(hand_color)
            pen_hand.setWidth(3)
            painter.setPen(pen_hand)
            for connection in mp.solutions.holistic.HAND_CONNECTIONS:
                painter.drawLine(hand_pts[connection[0]], hand_pts[connection[1]])
            painter.setBrush(hand_color)
            painter.setPen(Qt.PenStyle.NoPen)
            for pt in hand_pts:
                painter.drawEllipse(pt, 4, 4)

        draw_hand(self.pose_data.get("left_hand", []), QColor(0, 255, 0, 200))
        draw_hand(self.pose_data.get("right_hand", []), QColor(255, 165, 0, 200))
