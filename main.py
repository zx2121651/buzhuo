import sys
import time
import keyboard
import cv2
import mediapipe as mp
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QThread, Signal, QPointF
from PySide6.QtGui import QPainter, QColor, QPen

# 导入 1€ 滤波器
from one_euro_filter import PoseFilterManager

# --- 全局平滑配置参数 ---
# 您可以在这里微调 1€ Filter 的表现
FILTER_CONFIG = {
    "min_cutoff": 0.5,  # 控制低速时的平滑度 (值越小越平滑，但延迟增加)
    "beta": 0.01,  # 控制高速时的响应速度 (值越大响应越快，但容易抖动)
    "d_cutoff": 1.0,  # 速度平滑的截止频率 (一般保持 1.0 即可)
}


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

    def __init__(self, screen_width, screen_height, camera_index=0):
        super().__init__()
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.camera_index = camera_index
        self._is_running = True

        # 初始化 1€ 全身姿态滤波器
        self.pose_filter = PoseFilterManager(
            num_points=33,
            min_cutoff=FILTER_CONFIG["min_cutoff"],
            beta=FILTER_CONFIG["beta"],
            d_cutoff=FILTER_CONFIG["d_cutoff"],
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

                landmarks_pts = []
                if results.pose_landmarks:
                    # 当前时间戳 (用于 1€ Filter 计算速度)
                    current_t = time.time()

                    raw_points = []
                    # We process the detected full body pose
                    for landmark in results.pose_landmarks.landmark:
                        # Convert normalized coordinates [0.0, 1.0] to screen coordinates
                        # We stretch the camera view directly to the screen dimensions
                        screen_x = landmark.x * self.screen_width
                        screen_y = landmark.y * self.screen_height
                        raw_points.append((screen_x, screen_y))

                    # 应用 1€ 滤波器进行平滑处理
                    smoothed_points = self.pose_filter.process(raw_points, current_t)

                    # 将平滑后的坐标转换回 QPointF
                    for x_hat, y_hat in smoothed_points:
                        landmarks_pts.append(QPointF(x_hat, y_hat))
                else:
                    # 未检测到人体，必须重置滤波器的历史状态，避免重新捕捉时出现“瞬移拉扯”
                    self.pose_filter.reset()

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
    vision_thread.start()

    # Show the canvas
    overlay.show()

    # Execute application
    exit_code = app.exec()

    # Clean up threads
    vision_thread.stop()
    hotkey_thread.stop()

    sys.exit(exit_code)
