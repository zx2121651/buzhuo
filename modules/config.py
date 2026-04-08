import json
import os

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "input_mode": "camera",
    "camera_index": 0,
    "video_path": "dance.mp4",
    "video_loop": True,
    "min_cutoff": 0.5,
    "beta": 0.01,
    "d_cutoff": 1.0,
    "udp_enabled": True,
    "udp_ip": "127.0.0.1",
    "udp_port": 7001,
    "flip_x": False,
    "flip_y": False,
    "flip_z": False,
    # --- 高阶算法增强 (Algorithm Enhancements) ---
    "enable_global_depth": True,  # 开启绝对空间位移推算
    "ref_shoulder_width_m": 0.40,  # 物理标准肩宽参考值 (米)
    "camera_focal_length_px": 800.0,  # 摄像机等效焦距 (像素)
    "enable_head_pnp": True,  # 开启高精度头部姿态解算 (PnP)
    "enable_kinematic_constraints": True,  # 开启防畸变的运动学自适应骨骼缩放 (Kinematic Bone Rescaling)
    "kinematic_calibration_frames": 30,  # 启动时/重置时，取多少帧的平均值来精确测量真人的四肢长度
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
