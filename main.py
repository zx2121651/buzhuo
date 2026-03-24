import sys
import time
import keyboard
import random
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


class DataGeneratorThread(QThread):
    # Signal that emits the new (x, y) coordinate
    sig_data_updated = Signal(QPointF)

    def __init__(self, width, height):
        super().__init__()
        self.width = width
        self.height = height
        self._is_running = True

    def run(self):
        # Start at the center
        x, y = self.width / 2, self.height / 2

        while self._is_running:
            # Random walk
            dx = random.uniform(-10, 10)
            dy = random.uniform(-10, 10)

            x = max(0, min(self.width, x + dx))
            y = max(0, min(self.height, y + dy))

            # Emit the new position
            self.sig_data_updated.emit(QPointF(x, y))

            # ~60 FPS (1000ms / 60 ≈ 16ms)
            time.sleep(1 / 60)

    def stop(self):
        self._is_running = False
        self.wait()


class TransparentOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.dynamic_point = None
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

        # Initialize the target point to the center of the screen
        self.dynamic_point = QPointF(self.width() / 2, self.height() / 2)

    def update_dynamic_data(self, point: QPointF):
        """Slot to receive new data and trigger a repaint."""
        self.dynamic_point = point
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

        # 1. Static border drawing (to verify transparency bounds)
        pen_border = QPen(QColor(255, 0, 0, 100))
        pen_border.setWidth(10)
        painter.setPen(pen_border)
        painter.drawRect(5, 5, self.width() - 10, self.height() - 10)

        # 2. Dynamic drawing based on simulated mocap data
        if self.dynamic_point:
            # Draw a moving green circle
            painter.setBrush(QColor(0, 255, 0, 150))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(self.dynamic_point, 20, 20)

            # Draw a moving crosshair tracking the point
            pen_cross = QPen(QColor(0, 255, 0, 200))
            pen_cross.setWidth(3)
            painter.setPen(pen_cross)
            x, y = self.dynamic_point.x(), self.dynamic_point.y()
            painter.drawLine(x - 30, y, x + 30, y)
            painter.drawLine(x, y - 30, x, y + 30)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    overlay = TransparentOverlay()

    # 1. Setup Global Hotkeys
    hotkey_thread = GlobalHotkeyManager()
    hotkey_thread.sig_toggle_visibility.connect(overlay.toggle_visibility)
    hotkey_thread.sig_exit_app.connect(overlay.exit_application)
    hotkey_thread.start()

    # 2. Setup Dynamic Data Source (~60FPS Mocap Simulator)
    data_thread = DataGeneratorThread(overlay.width(), overlay.height())
    data_thread.sig_data_updated.connect(overlay.update_dynamic_data)
    data_thread.start()

    # Show the canvas
    overlay.show()

    # Execute application
    exit_code = app.exec()

    # Clean up threads
    data_thread.stop()
    hotkey_thread.stop()

    sys.exit(exit_code)
