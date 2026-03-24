import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

import sys
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QSpacerItem,
    QSizePolicy,
)
from PyQt6.QtCore import Qt


class PoseCaptureThread(QThread):
    change_pixmap_signal = pyqtSignal(QImage)

    def __init__(self):
        import os
        import urllib.request

        model_path = "pose_landmarker_full.task"
        if not os.path.exists(model_path):
            url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task"
            urllib.request.urlretrieve(url, model_path)
        super().__init__()
        self._run_flag = True

        # Initialize the PoseLandmarker
        base_options = python.BaseOptions(model_asset_path="pose_landmarker_full.task")
        options = vision.PoseLandmarkerOptions(
            base_options=base_options, running_mode=vision.RunningMode.VIDEO
        )
        self.detector = vision.PoseLandmarker.create_from_options(options)

    def run(self):
        cap = cv2.VideoCapture(0)

        while self._run_flag:
            ret, frame = cap.read()
            if not ret:
                continue

            # Convert to RGB and wrap into MediaPipe Image
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

            # Timestamp for VIDEO mode
            timestamp_ms = int(cap.get(cv2.CAP_PROP_POS_MSEC))
            if timestamp_ms <= getattr(self, "last_timestamp_ms", -1):
                timestamp_ms = getattr(self, "last_timestamp_ms", -1) + 1
            self.last_timestamp_ms = timestamp_ms

            # Make detection
            # Make detection
            detection_result = self.detector.detect_for_video(mp_image, timestamp_ms)

            # Draw landmarks (since mp.solutions is not directly available, draw manually or just show feed)
            if detection_result.pose_landmarks:
                for pose_landmarks in detection_result.pose_landmarks:
                    for landmark in pose_landmarks:
                        x = int(landmark.x * frame.shape[1])
                        y = int(landmark.y * frame.shape[0])
                        cv2.circle(rgb_frame, (x, y), 5, (0, 255, 0), -1)

            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w
            convert_to_Qt_format = QImage(
                rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888
            )
            p = convert_to_Qt_format.scaled(
                800, 600, aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio
            )
            self.change_pixmap_signal.emit(p)

        cap.release()
        self.detector.close()

    def stop(self):
        self._run_flag = False
        self.wait()


class TechnicalAtelier(QMainWindow):
    def __init__(self):
        import os
        import urllib.request

        model_path = "pose_landmarker_full.task"
        if not os.path.exists(model_path):
            url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task"
            urllib.request.urlretrieve(url, model_path)
        super().__init__()
        self.setWindowTitle("Technical Atelier")
        self.setGeometry(100, 100, 1280, 720)
        self.setStyleSheet("""
            QWidget { background-color: #0e0e0e; color: #e7e5e5; font-family: Inter, sans-serif; }
        """)

        # Central Widget & Main Layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.setup_sidebar()
        self.setup_right_panel()

    def setup_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(240)
        self.sidebar.setStyleSheet("""
            QFrame { background-color: #131313; border-right: 1px solid #252626; border-top: none; border-bottom: none; border-left: none; }
        """)
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(20, 20, 20, 20)
        self.sidebar_layout.setSpacing(10)

        # App Title
        app_title = QLabel("Technical Atelier")
        app_title.setStyleSheet(
            "font-family: 'Space Grotesk', sans-serif; font-size: 18px; font-weight: bold; color: #ffffff; border: none; margin-bottom: 20px;"
        )
        self.sidebar_layout.addWidget(app_title)

        # App Info
        app_info_layout = QHBoxLayout()
        app_info_layout.setContentsMargins(0, 0, 0, 0)
        icon_label = QLabel("T")
        icon_label.setFixedSize(30, 30)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet(
            "background-color: #ffb4ab; color: #93000a; border-radius: 4px; font-weight: bold; border: none;"
        )

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(5, 0, 0, 0)
        title_label = QLabel("PRECISION")
        title_label.setStyleSheet(
            "font-family: 'Space Grotesk', sans-serif; font-size: 12px; font-weight: bold; color: #e7e5e5; border: none;"
        )
        version_label = QLabel("v2.4.0")
        version_label.setStyleSheet("font-size: 10px; color: #acabaa; border: none;")
        text_layout.addWidget(title_label)
        text_layout.addWidget(version_label)
        text_layout.setSpacing(0)

        app_info_layout.addWidget(icon_label)
        app_info_layout.addLayout(text_layout)
        app_info_layout.addStretch()

        app_info_widget = QWidget()
        app_info_widget.setStyleSheet("border:none;")
        app_info_widget.setLayout(app_info_layout)
        self.sidebar_layout.addWidget(app_info_widget)

        self.sidebar_layout.addSpacing(20)

        # Navigation Links
        nav_items = [
            ("RECORD", "#ffb4ab", True),  # Active
            ("EDITOR", "#acabaa", False),
            ("HISTORY", "#acabaa", False),
            ("CLOUD", "#acabaa", False),
        ]

        for text, color, active in nav_items:
            btn = QPushButton(text)
            bg_color = "#1f2020" if active else "transparent"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg_color};
                    color: {color};
                    border: none;
                    text-align: left;
                    padding: 10px 15px;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: {'bold' if active else 'normal'};
                }}
                QPushButton:hover {{
                    background-color: #1f2020;
                }}
            """)
            self.sidebar_layout.addWidget(btn)

        # Spacer
        self.sidebar_layout.addSpacerItem(
            QSpacerItem(
                20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
            )
        )

        # New Capture Button
        new_capture_btn = QPushButton("NEW CAPTURE")
        new_capture_btn.setFixedHeight(40)
        new_capture_btn.setStyleSheet("""
            QPushButton {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffb4ab, stop:1 #93000a);
                color: #490013;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffc7c0, stop:1 #bb0010);
            }
        """)
        self.sidebar_layout.addWidget(new_capture_btn)

        self.main_layout.addWidget(self.sidebar)

    def setup_right_panel(self):
        self.right_panel = QWidget()
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(0)

        self.setup_header()
        self.setup_central_area()
        self.setup_footer()

        self.main_layout.addWidget(self.right_panel)

    def setup_header(self):
        self.header = QFrame()
        self.header.setFixedHeight(60)
        self.header.setStyleSheet(
            "background-color: #131313; border-bottom: 1px solid #252626; border-top: none; border-left: none; border-right: none;"
        )
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(20, 0, 20, 0)
        self.header_layout.setSpacing(20)

        # Tabs
        tabs_layout = QHBoxLayout()
        tabs_layout.setContentsMargins(0, 0, 0, 0)
        tabs_layout.setSpacing(20)

        tab_names = ["Captures", "Library", "Templates"]
        for i, name in enumerate(tab_names):
            lbl = QLabel(name)
            if i == 0:
                lbl.setStyleSheet(
                    "color: #e7e5e5; border:none; border-bottom: 2px solid #ffb4ab; padding-bottom: 5px; font-size: 13px; font-weight: bold;"
                )
            else:
                lbl.setStyleSheet("color: #acabaa; border:none; font-size: 13px;")
            tabs_layout.addWidget(lbl)

        tabs_widget = QWidget()
        tabs_widget.setStyleSheet("border:none;")
        tabs_widget.setLayout(tabs_layout)
        self.header_layout.addWidget(tabs_widget)

        self.header_layout.addStretch()

        # Top right icons
        icons_layout = QHBoxLayout()
        icons_layout.setContentsMargins(0, 0, 0, 0)
        icons_layout.setSpacing(15)

        for icon in ["?", "⚙", "U"]:
            btn = QPushButton(icon)
            btn.setFixedSize(30, 30)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #acabaa;
                    border: none;
                    font-size: 16px;
                }
                QPushButton:hover {
                    color: #e7e5e5;
                }
            """)
            icons_layout.addWidget(btn)

        icons_widget = QWidget()
        icons_widget.setStyleSheet("border:none;")
        icons_widget.setLayout(icons_layout)
        self.header_layout.addWidget(icons_widget)

        self.right_layout.addWidget(self.header)

        # Status Bar under header
        self.status_bar = QFrame()
        self.status_bar.setFixedHeight(60)
        self.status_bar.setStyleSheet("background-color: #0e0e0e; border: none;")
        self.status_layout = QHBoxLayout(self.status_bar)
        self.status_layout.setContentsMargins(20, 10, 20, 10)

        # Resolution
        res_layout = QVBoxLayout()
        res_layout.setContentsMargins(0, 0, 0, 0)
        res_layout.setSpacing(2)
        res_label = QLabel("ACTIVE REGION")
        res_label.setStyleSheet(
            "color: #acabaa; font-size: 10px; text-transform: uppercase; font-weight: bold;"
        )
        res_value = QLabel(
            "1920 × 1080  <span style='color:#ffb4ab; font-size:12px; font-weight:normal;'>Capturing...</span>"
        )
        res_value.setStyleSheet(
            "font-family: 'Space Grotesk', sans-serif; font-size: 18px; font-weight: bold; color: #ffffff;"
        )
        res_layout.addWidget(res_label)
        res_layout.addWidget(res_value)

        res_widget = QWidget()
        res_widget.setStyleSheet("border:none;")
        res_widget.setLayout(res_layout)
        self.status_layout.addWidget(res_widget)

        self.status_layout.addStretch()

        # Timer and FPS
        timer_layout = QHBoxLayout()
        timer_layout.setContentsMargins(0, 0, 0, 0)
        timer_layout.setSpacing(10)

        timer_btn = QPushButton("  00:12:45")
        timer_btn.setStyleSheet("""
            QPushButton {
                background-color: #1f2020;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 8px 15px;
                font-family: 'Space Grotesk', sans-serif;
                font-size: 14px;
                font-weight: bold;
            }
        """)

        fps_btn = QPushButton("  60.0 FPS")
        fps_btn.setStyleSheet("""
            QPushButton {
                background-color: #1f2020;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 8px 15px;
                font-family: 'Space Grotesk', sans-serif;
                font-size: 14px;
                font-weight: bold;
            }
        """)

        timer_layout.addWidget(timer_btn)
        timer_layout.addWidget(fps_btn)

        timer_widget = QWidget()
        timer_widget.setStyleSheet("border:none;")
        timer_widget.setLayout(timer_layout)
        self.status_layout.addWidget(timer_widget)

        self.right_layout.addWidget(self.status_bar)

    def setup_central_area(self):
        self.central_area = QFrame()
        self.central_area.setStyleSheet("background-color: #0e0e0e; border: none;")
        self.central_area_layout = QVBoxLayout(self.central_area)
        self.central_area_layout.setContentsMargins(20, 0, 20, 20)

        # Frame for recording area
        self.record_frame = QFrame()
        self.record_frame.setStyleSheet("""
            QFrame {
                border: 2px solid #484848;
                border-radius: 8px;
                background-color: transparent;
            }
        """)
        self.record_layout = QVBoxLayout(self.record_frame)
        self.record_layout.setContentsMargins(0, 0, 0, 0)

        # Internal Content of Recording Area
        self.record_content = QFrame()
        self.record_content.setStyleSheet("""
            QFrame {
                background-color: rgba(37, 38, 38, 150);
                border-radius: 8px;
                border: none;
            }
        """)
        self.content_layout = QVBoxLayout(self.record_content)

        # We will add a QLabel to display the video feed
        self.video_label = QLabel("CAMERA FEED")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: transparent; color: #acabaa;")
        self.content_layout.addWidget(self.video_label, 1)  # Add with stretch factor 1

        # Setup Thread
        self.thread = PoseCaptureThread()
        self.thread.change_pixmap_signal.connect(self.update_image)
        self.thread.start()

        # Floating Toolbar at bottom
        toolbar_container = QHBoxLayout()
        toolbar_container.addStretch()

        self.toolbar = QFrame()
        self.toolbar.setFixedSize(300, 70)
        self.toolbar.setStyleSheet("""
            QFrame {
                background-color: #252626;
                border-radius: 12px;
                border: 1px solid #484848;
            }
        """)
        self.toolbar_layout = QHBoxLayout(self.toolbar)
        self.toolbar_layout.setContentsMargins(15, 5, 15, 5)
        self.toolbar_layout.setSpacing(20)

        # Record Button
        record_btn = QPushButton("●")
        record_btn.setFixedSize(50, 50)
        record_btn.setStyleSheet("""
            QPushButton {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffb4ab, stop:1 #93000a);
                color: #ffffff;
                border-radius: 25px;
                font-size: 20px;
                border: none;
            }
        """)
        self.toolbar_layout.addWidget(record_btn)

        # Stop Button
        stop_layout = QVBoxLayout()
        stop_btn = QPushButton("■")
        stop_btn.setFixedSize(30, 30)
        stop_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #e7e5e5; font-size: 16px; border: none; }"
        )
        stop_lbl = QLabel("STOP")
        stop_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stop_lbl.setStyleSheet("font-size: 9px; color: #acabaa; border: none;")
        stop_layout.addWidget(stop_btn)
        stop_layout.addWidget(stop_lbl)
        stop_widget = QWidget()
        stop_widget.setStyleSheet("border:none;")
        stop_widget.setLayout(stop_layout)
        self.toolbar_layout.addWidget(stop_widget)

        # Pause Button
        pause_layout = QVBoxLayout()
        pause_btn = QPushButton("⏸")
        pause_btn.setFixedSize(30, 30)
        pause_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #e7e5e5; font-size: 16px; border: none; }"
        )
        pause_lbl = QLabel("PAUSE")
        pause_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pause_lbl.setStyleSheet("font-size: 9px; color: #acabaa; border: none;")
        pause_layout.addWidget(pause_btn)
        pause_layout.addWidget(pause_lbl)
        pause_widget = QWidget()
        pause_widget.setStyleSheet("border:none;")
        pause_widget.setLayout(pause_layout)
        self.toolbar_layout.addWidget(pause_widget)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setStyleSheet(
            "color: #484848; border: 1px solid #484848; background-color: #484848;"
        )
        divider.setFixedWidth(1)
        self.toolbar_layout.addWidget(divider)

        # Config Button
        config_layout = QVBoxLayout()
        config_btn = QPushButton("⚙")
        config_btn.setFixedSize(30, 30)
        config_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #e7e5e5; font-size: 16px; border: none; }"
        )
        config_lbl = QLabel("CONFIG")
        config_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        config_lbl.setStyleSheet("font-size: 9px; color: #acabaa; border: none;")
        config_layout.addWidget(config_btn)
        config_layout.addWidget(config_lbl)
        config_widget = QWidget()
        config_widget.setStyleSheet("border:none;")
        config_widget.setLayout(config_layout)
        self.toolbar_layout.addWidget(config_widget)

        toolbar_container.addWidget(self.toolbar)
        toolbar_container.addStretch()
        self.content_layout.addLayout(toolbar_container)

        self.record_layout.addWidget(self.record_content)
        self.central_area_layout.addWidget(self.record_frame)

        self.right_layout.addWidget(self.central_area)

    def update_image(self, qt_image):
        self.video_label.setPixmap(QPixmap.fromImage(qt_image))

    def closeEvent(self, event):
        if hasattr(self, "thread"):
            self.thread.stop()
        event.accept()

    def setup_footer(self):
        self.footer = QFrame()
        self.footer.setFixedHeight(30)
        self.footer.setStyleSheet(
            "background-color: #131313; border-top: 1px solid #252626; border-bottom: none; border-left: none; border-right: none;"
        )
        self.footer_layout = QHBoxLayout(self.footer)
        self.footer_layout.setContentsMargins(10, 0, 10, 0)

        # Bottom left stats
        stats_label = QLabel("GPU: 12%    RAM: 1.2 GB    DISK: 245 GB FREE")
        stats_label.setStyleSheet("color: #acabaa; font-size: 10px; border: none;")
        self.footer_layout.addWidget(stats_label)

        self.footer_layout.addStretch()

        # Bottom right icons
        right_stats = QLabel("EN-US    ⚙    □")
        right_stats.setStyleSheet("color: #acabaa; font-size: 10px; border: none;")
        self.footer_layout.addWidget(right_stats)

        self.right_layout.addWidget(self.footer)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TechnicalAtelier()
    window.show()
    sys.exit(app.exec())
