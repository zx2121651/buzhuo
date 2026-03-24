import sys
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen


class TransparentOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        # 设置窗口标志：
        # FramelessWindowHint: 移除窗口边框和标题栏
        # WindowStaysOnTopHint: 窗口始终置顶
        # WindowTransparentForInput: 鼠标事件穿透
        # Tool: 不在任务栏显示图标 (可选，但对于此类覆盖层很有用)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.Tool
        )

        # 设置窗口背景透明
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 获取主显示器并设置窗口全屏覆盖主显示器
        screen = QApplication.primaryScreen()
        geometry = screen.geometry()
        self.setGeometry(geometry)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center_x = self.width() // 2
        center_y = self.height() // 2

        # 绘制半透明红色十字准星
        pen = QPen(QColor(255, 0, 0, 150))
        pen.setWidth(5)
        painter.setPen(pen)
        painter.drawLine(center_x - 50, center_y, center_x + 50, center_y)
        painter.drawLine(center_x, center_y - 50, center_x, center_y + 50)

        # 绘制半透明红色边框
        pen_border = QPen(QColor(255, 0, 0, 100))
        pen_border.setWidth(10)
        painter.setPen(pen_border)
        painter.drawRect(5, 5, self.width() - 10, self.height() - 10)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    overlay = TransparentOverlay()
    overlay.show()
    sys.exit(app.exec())
