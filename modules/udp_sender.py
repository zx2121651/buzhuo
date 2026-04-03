import socket
import json
from PySide6.QtCore import QThread, Signal


class UdpSender(QThread):
    """
    非阻塞式 UDP 异步发送服务
    将 3D 动捕数据以 JSON 格式发送给下游 3D 引擎，同时触发 UI 的心跳状态灯
    """

    sig_heartbeat = Signal()

    def __init__(self, ip, port):
        super().__init__()
        self.ip = ip
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 设为非阻塞模式，防止网络波动卡死主线程
        self.sock.setblocking(False)

    def send(self, data_list):
        try:
            # 包装为字典，方便 Unity 的 JsonUtility 反序列化
            payload = {"landmarks": data_list}
            msg = json.dumps(payload, separators=(",", ":"))
            self.sock.sendto(msg.encode("utf-8"), (self.ip, self.port))
            self.sig_heartbeat.emit()
        except BlockingIOError:
            # 发送缓冲区满，丢弃该帧不阻塞当前线程
            pass
        except Exception as e:
            print(f"[UDP] 发送错误: {e}")

    def update_address(self, ip, port):
        self.ip = ip
        self.port = port

    def close(self):
        self.sock.close()
