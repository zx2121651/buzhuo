import sys
import time
import keyboard
import cv2
import mediapipe as mp
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QThread, Signal, QPointF
from PySide6.QtGui import QPainter, QColor, QPen

# 导入配置和滤波器
import config
from one_euro_filter import PoseFilterManager

# 加载配置
APP_CONFIG = config.load_config()


class GlobalHotkeyManager(QThread):
    # Signals to communicate with the main UI thread
    sig_toggle_visibility = Signal()
    sig_exit_app = Signal()

    def run(self):
        # Register global hotkeys
        # We run this in a separate thread so it doesn't block the UI
        keyboard.add_hotkey("insert", self.sig_toggle_visibility.emit)
        keyboard.add_hotkey("end", self.sig_exit_app.emit)

        # Keep the thread alive
        keyboard.wait()

    def stop(self):
        keyboard.unhook_all()
        self.terminate()


class VisionCaptureThread(QThread):
    # Signal that emits a list of mapped (x, y) coordinates for the 33 body landmarks
    # Emits an empty list if no body is detected
    sig_pose_data_updated = Signal(list)

    # 新增信号：发射用于下游 (如 3D 引擎) 的纯净 3D 数据列表
    sig_3d_data_ready = Signal(list)

    def __init__(self, screen_width, screen_height, camera_index=0):
        super().__init__()
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.camera_index = camera_index
        self._is_running = True

        # 初始化 1€ 全身姿态滤波器
        # 用于 2D 屏幕渲染的滤波器 (X, Y 归一化坐标平滑，Z 直接透传补0)
        self.ui_pose_filter = PoseFilterManager(
            num_points=33,
            min_cutoff=APP_CONFIG["min_cutoff"],
            beta=APP_CONFIG["beta"],
            d_cutoff=APP_CONFIG["d_cutoff"],
        )

        # 用于 3D 引擎输出的滤波器 (真实物理世界坐标平滑)
        self.world_pose_filter = PoseFilterManager(
            num_points=33,
            min_cutoff=APP_CONFIG["min_cutoff"],
            beta=APP_CONFIG["beta"],
            d_cutoff=APP_CONFIG["d_cutoff"],
        )

        # Initialize MediaPipe Pose
        self.mp_pose = mp.solutions.pose

    def run(self):
        cap = cv2.VideoCapture(self.camera_index)

        # Optimize performance: static_image_mode=False for video streams
        with self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        ) as pose:
            while self._is_running and cap.isOpened():
                success, image = cap.read()
                if not success:
                    # If reading frame fails, sleep briefly and try again
                    time.sleep(0.01)
                    continue

                # To improve performance, optionally mark the image as not writeable to pass by reference.
                image.flags.writeable = False

                # Flip the image horizontally for a later selfie-view display, and convert the BGR image to RGB.
                image = cv2.cvtColor(cv2.flip(image, 1), cv2.COLOR_BGR2RGB)

                # Process the image and detect pose
                results = pose.process(image)

                landmarks_pts = []  # 用于 UI
                world_data_list = []  # 用于 3D 引擎输出

                if results.pose_landmarks and results.pose_world_landmarks:
                    current_t = time.time()

                    # === 1. 处理用于 UI 渲染的 2D 坐标映射 ===
                    ui_raw_points = []
                    for landmark in results.pose_landmarks.landmark:
                        # 暂时补全 Z 轴为了适配 3D 滤波器，我们实际只关心 x, y 平滑
                        ui_raw_points.append((landmark.x, landmark.y, 0.0))

                    ui_smoothed = self.ui_pose_filter.process(ui_raw_points, current_t)

                    for x_hat, y_hat, _ in ui_smoothed:
                        screen_x = x_hat * self.screen_width
                        screen_y = y_hat * self.screen_height
                        landmarks_pts.append(QPointF(screen_x, screen_y))

                    # === 2. 处理用于下游引擎的 3D 物理世界坐标输出 ===
                    world_raw_points = []
                    visibility_list = []
                    for landmark in results.pose_world_landmarks.landmark:
                        world_raw_points.append((landmark.x, landmark.y, landmark.z))
                        visibility_list.append(landmark.visibility)

                    world_smoothed = self.world_pose_filter.process(
                        world_raw_points, current_t
                    )

                    # 组装最终输出的 List[Dict] 数据结构
                    for i, (x_hat, y_hat, z_hat) in enumerate(world_smoothed):
                        world_data_list.append(
                            {
                                "id": i,
                                "x": x_hat,
                                "y": y_hat,
                                "z": z_hat,
                                "visibility": visibility_list[i],
                            }
                        )

                    self.sig_3d_data_ready.emit(world_data_list)
                else:
                    # 丢失目标，重置滤波器
                    self.ui_pose_filter.reset()
                    self.world_pose_filter.reset()

                # Emit the extracted data (list of QPointF, or empty list if no pose)
                self.sig_pose_data_updated.emit(landmarks_pts)

        # Release resources
        cap.release()

    def stop(self):
        self._is_running = False
        self.wait()


class TransparentOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.pose_landmarks = []  # List of QPointF representing the 33 body joints
        self.initUI()

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

    def update_pose_data(self, landmarks: list):
        """Slot to receive new pose data and trigger a repaint."""
        self.pose_landmarks = landmarks
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

        # Draw body skeleton if landmarks are available
        if self.pose_landmarks and len(self.pose_landmarks) == 33:
            # MediaPipe Pose Landmark Connections (Topology)
            connections = list(mp.solutions.pose.POSE_CONNECTIONS)

            # 1. Draw Bones (lines)
            pen_bone = QPen(QColor(0, 255, 255, 180))  # Cyan bones
            pen_bone.setWidth(4)
            painter.setPen(pen_bone)
            for connection in connections:
                pt1 = self.pose_landmarks[connection[0]]
                pt2 = self.pose_landmarks[connection[1]]
                painter.drawLine(pt1, pt2)

            # 2. Draw Joints (circles)
            painter.setBrush(QColor(255, 0, 0, 200))
            painter.setPen(Qt.PenStyle.NoPen)
            for pt in self.pose_landmarks:
                painter.drawEllipse(pt, 6, 6)

            # 3. Draw a larger circle at the nose (landmark 0) for the head
            nose = self.pose_landmarks[0]
            painter.setBrush(QColor(255, 255, 0, 150))  # Yellow head
            painter.drawEllipse(nose, 20, 20)

            # 4. Draw distinct circles for the hands (left: 15/19, right: 16/20)
            # We use the index fingers (19 and 20) for hand tracking cursors
            left_index = self.pose_landmarks[19]
            right_index = self.pose_landmarks[20]
            painter.setBrush(QColor(0, 200, 255, 150))  # Blue cursors
            painter.drawEllipse(left_index, 15, 15)
            painter.drawEllipse(right_index, 15, 15)


def on_3d_data_ready(data):
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

    vision_thread.start()

    # Show the canvas
    overlay.show()

    # Execute application
    exit_code = app.exec()

    # Clean up threads
    vision_thread.stop()
    hotkey_thread.stop()

    sys.exit(exit_code)
