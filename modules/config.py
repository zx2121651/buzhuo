import json
import os

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "input_mode": "camera",  # "camera" 或 "video"
    "camera_index": 0,  # 摄像头索引 (如 0, 1)
    "video_path": "dance.mp4",  # 输入视频文件路径
    "video_loop": True,  # 视频播放完毕后是否循环
    "min_cutoff": 0.5,  # 1€ Filter 低速平滑度
    "beta": 0.01,  # 1€ Filter 高速响应度
    "d_cutoff": 1.0,  # 1€ Filter 速度平滑截止频率
    "udp_enabled": True,  # 是否发送 UDP 数据
    "udp_ip": "127.0.0.1",  # UDP 目标 IP
    "udp_port": 7001,  # UDP 目标端口
    "flip_x": False,  # 坐标系 X 翻转
    "flip_y": False,  # 坐标系 Y 翻转
    "flip_z": False,  # 坐标系 Z 翻转
    # --- 高阶算法增强 (Algorithm Enhancements) ---
    "enable_global_depth": True,  # 开启绝对空间位移推算
    "ref_shoulder_width_m": 0.40,  # 物理标准肩宽参考值 (米)
    "camera_focal_length_px": 800.0,  # 摄像机等效焦距 (像素)
    "enable_head_pnp": True,  # 开启高精度头部姿态解算 (PnP)
}


def load_config():
    """加载配置文件，如果不存在则创建默认配置"""
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in config:
                    config[k] = v
            return config
    except Exception as e:
        print(f"[Config] Error loading {CONFIG_FILE}: {e}. Using default config.")
        return DEFAULT_CONFIG


def save_config(config):
    """保存配置到文件"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
