import keyboard
from PySide6.QtCore import QThread, Signal


class GlobalHotkeyManager(QThread):
    """
    全局快捷键管理器
    通过后台线程监听键盘事件，不阻塞主线程。
    - Insert 键：切换 UI 显示/隐藏
    - End 键：安全退出程序
    """

    sig_toggle_visibility = Signal()
    sig_exit_app = Signal()

    def run(self):
        keyboard.add_hotkey("insert", self.sig_toggle_visibility.emit)
        keyboard.add_hotkey("end", self.sig_exit_app.emit)
        keyboard.wait()

    def stop(self):
        keyboard.unhook_all()
        self.terminate()
