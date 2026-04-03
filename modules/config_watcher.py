import os
import time
from PySide6.QtCore import QThread, Signal
from modules import config


class ConfigWatcher(QThread):
    """
    配置文件热重载监控器
    定时检查 config.json 文件的修改时间，发生改变时触发信号
    """

    sig_config_reloaded = Signal(dict)

    def __init__(self, config_file="config.json", interval_ms=1000):
        super().__init__()
        self.config_file = config_file
        self.interval_ms = interval_ms
        self._is_running = True
        self._last_mtime = 0
        if os.path.exists(self.config_file):
            self._last_mtime = os.path.getmtime(self.config_file)

    def run(self):
        while self._is_running:
            try:
                if os.path.exists(self.config_file):
                    current_mtime = os.path.getmtime(self.config_file)
                    if current_mtime > self._last_mtime:
                        self._last_mtime = current_mtime
                        new_config = config.load_config()
                        self.sig_config_reloaded.emit(new_config)
                        print("[Config] Reloaded configuration automatically.")
            except Exception as e:
                print(f"[Config] Error checking file: {e}")

            time.sleep(self.interval_ms / 1000.0)

    def stop(self):
        self._is_running = False
        self.wait()
