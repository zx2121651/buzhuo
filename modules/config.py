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
    "enable_global_depth": True,
    "ref_shoulder_width_m": 0.40,
    "camera_focal_length_px": 800.0,
    "enable_head_pnp": True,
    "enable_kinematic_constraints": True,
    "kinematic_calibration_frames": 30,
    "enable_kalman_prediction": True,  # 开启四肢末端的高速卡尔曼惯性预测
    "kalman_process_noise": 0.01,  # 卡尔曼过程噪声(物理信任度，越小越相信惯性)
    "kalman_measurement_noise": 0.1,  # 卡尔曼测量噪声(摄像头信任度，越大越平滑但延迟高)
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
