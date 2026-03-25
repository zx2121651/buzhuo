import sys
import time
import keyboard
import cv2
import mediapipe as mp
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, QThread, Signal, QPointF
from PySide6.QtGui import QPainter, QColor, QPen


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
    # Signal that emits a list of mapped (x, y) coordinates for the 21 hand landmarks
    # Emits an empty list if no hand is detected
    sig_hand_data_updated = Signal(list)

    def __init__(self, screen_width, screen_height, camera_index=0):
        super().__init__()
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.camera_index = camera_index
        self._is_running = True

        # Initialize MediaPipe Hands
        self.mp_hands = mp.solutions.hands

    def run(self):
        cap = cv2.VideoCapture(self.camera_index)

        # Optimize performance: static_image_mode=False for video streams
        with self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        ) as hands:
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

                # Process the image and detect hands
                results = hands.process(image)

                landmarks_pts = []
                if results.multi_hand_landmarks:
                    # We only process the first detected hand (since max_num_hands=1)
                    hand_landmarks = results.multi_hand_landmarks[0]
                    for landmark in hand_landmarks.landmark:
                        # Convert normalized coordinates [0.0, 1.0] to screen coordinates
                        # We stretch the camera view directly to the screen dimensions
                        screen_x = landmark.x * self.screen_width
                        screen_y = landmark.y * self.screen_height
                        landmarks_pts.append(QPointF(screen_x, screen_y))

                # Emit the extracted data (list of QPointF, or empty list if no hand)
                self.sig_hand_data_updated.emit(landmarks_pts)

        # Release resources
        cap.release()

    def stop(self):
        self._is_running = False
        self.wait()


class TransparentOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.hand_landmarks = []  # List of QPointF representing the 21 joints
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

    def update_hand_data(self, landmarks: list):
        """Slot to receive new hand data and trigger a repaint."""
        self.hand_landmarks = landmarks
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

        # Draw hand skeleton if landmarks are available
        if self.hand_landmarks and len(self.hand_landmarks) == 21:
            # MediaPipe Hand Landmark Connections (Topology)
            connections = [
                (0, 1),
                (1, 2),
                (2, 3),
                (3, 4),  # Thumb
                (0, 5),
                (5, 6),
                (6, 7),
                (7, 8),  # Index finger
                (5, 9),
                (9, 10),
                (10, 11),
                (11, 12),  # Middle finger
                (9, 13),
                (13, 14),
                (14, 15),
                (15, 16),  # Ring finger
                (13, 17),
                (0, 17),
                (17, 18),
                (18, 19),
                (19, 20),  # Pinky
            ]

            # 1. Draw Bones (lines)
            pen_bone = QPen(QColor(0, 255, 0, 180))
            pen_bone.setWidth(4)
            painter.setPen(pen_bone)
            for connection in connections:
                pt1 = self.hand_landmarks[connection[0]]
                pt2 = self.hand_landmarks[connection[1]]
                painter.drawLine(pt1, pt2)

            # 2. Draw Joints (circles)
            painter.setBrush(QColor(255, 0, 0, 200))
            painter.setPen(Qt.PenStyle.NoPen)
            for pt in self.hand_landmarks:
                painter.drawEllipse(pt, 6, 6)

            # 3. Draw a larger circle at the index finger tip (landmark 8) for a "cursor" effect
            index_tip = self.hand_landmarks[8]
            painter.setBrush(QColor(0, 200, 255, 150))
            painter.drawEllipse(index_tip, 15, 15)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    overlay = TransparentOverlay()

    # Setup Global Hotkeys
    hotkey_thread = GlobalHotkeyManager()
    hotkey_thread.sig_toggle_visibility.connect(overlay.toggle_visibility)
    hotkey_thread.sig_exit_app.connect(overlay.exit_application)
    hotkey_thread.start()

    # Setup Computer Vision Tracking (OpenCV + MediaPipe)
    vision_thread = VisionCaptureThread(
        overlay.width(), overlay.height(), camera_index=0
    )
    vision_thread.sig_hand_data_updated.connect(overlay.update_hand_data)
    vision_thread.start()

    # Show the canvas
    overlay.show()

    # Execute application
    exit_code = app.exec()

    # Clean up threads
    vision_thread.stop()
    hotkey_thread.stop()

    sys.exit(exit_code)
