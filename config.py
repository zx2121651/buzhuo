import json
import os

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "min_cutoff": 0.5,
    "beta": 0.01,
    "d_cutoff": 1.0,
    "udp_enabled": True,  # 默认开启 UDP
    "udp_ip": "127.0.0.1",
    "udp_port": 7001,
    "flip_x": False,  # 适配不同 3D 引擎的坐标系
    "flip_y": False,  # 通常情况 MediaPipe 原点在骨盆，Y向下为正，多数引擎 Y 向上为正
    "flip_z": False,  # MediaPipe Z 轴指向摄像机为负，某些引擎需要翻转
}


def load_config():
    """加载配置文件，如果不存在则创建默认配置"""
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            # 合并默认配置，防止用户删除了某些必需字段
            for k, v in DEFAULT_CONFIG.items():
                if k not in config:
                    config[k] = v
            return config
    except Exception as e:
        print(f"Error loading {CONFIG_FILE}: {e}. Using default config.")
        return DEFAULT_CONFIG


def save_config(config):
    """保存配置到文件"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
