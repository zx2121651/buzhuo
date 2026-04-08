import cv2
import time
import os
import math
import numpy as np
import mediapipe as mp
from PySide6.QtCore import QThread, Signal, QPointF
from one_euro_filter import PoseFilterManager

# 标准人脸的 3D 参考坐标 (单位: 毫米)
FACE_3D_MODEL_POINTS = np.array(
    [
        (0.0, 0.0, 0.0),  # Nose tip
        (0.0, -330.0, -65.0),  # Chin
        (-225.0, 170.0, -135.0),  # Left eye left corner
        (225.0, 170.0, -135.0),  # Right eye right corner
        (-150.0, -150.0, -125.0),  # Left Mouth corner
        (150.0, -150.0, -125.0),  # Right mouth corner
    ],
    dtype=np.float64,
)


class VisionCaptureThread(QThread):
    """
    核心视觉与动捕解算线程
    支持 Camera (实时) 与 Video (离线MP4) 两种输入模式。
    包含 MediaPipe Holistic 模型和 1€ Filter 平滑。
    """

    sig_pose_data_updated = Signal(dict)
    sig_3d_data_ready = Signal(dict)

    def __init__(self, screen_width, screen_height, initial_config):
        super().__init__()
        self.screen_width = screen_width
        self.screen_height = screen_height
        self._is_running = True
        self.current_config = initial_config.copy()

        self._init_filters(self.current_config)
        self.mp_holistic = mp.solutions.holistic

        self.calibration_count = 0
        self.fixed_bone_lengths = {}
        self.kinematic_chains = [
            (11, 13),  # 左肩(11) -> 左肘(13)
            (13, 15),  # 左肘(13) -> 左腕(15)
            (12, 14),  # 右肩(12) -> 右肘(14)
            (14, 16),  # 右肘(14) -> 右腕(16)
            (23, 25),  # 左髋(23) -> 左膝(25)
            (25, 27),  # 左膝(25) -> 左踝(27)
            (24, 26),  # 右髋(24) -> 右膝(26)
            (26, 28),  # 右膝(26) -> 右踝(28)
        ]

    def _init_filters(self, conf):
        min_c = conf.get("min_cutoff", 0.5)
        beta = conf.get("beta", 0.01)
        d_c = conf.get("d_cutoff", 1.0)

        self.ui_pose_filter = PoseFilterManager(33, min_c, beta, d_c)
        self.ui_face_filter = PoseFilterManager(468, min_c, beta, d_c)
        self.ui_lh_filter = PoseFilterManager(21, min_c, beta, d_c)
        self.ui_rh_filter = PoseFilterManager(21, min_c, beta, d_c)

        self.world_pose_filter = PoseFilterManager(33, min_c, beta, d_c)
        self.world_face_filter = PoseFilterManager(468, min_c, beta, d_c)
        self.world_lh_filter = PoseFilterManager(21, min_c, beta, d_c)
        self.world_rh_filter = PoseFilterManager(21, min_c, beta, d_c)

        self.global_root_filter = PoseFilterManager(1, min_c, beta, d_c)
        self.head_pose_filter = PoseFilterManager(1, min_c, beta, d_c)

    def update_config(self, new_config: dict):
        self.current_config = new_config.copy()
        min_c = new_config.get("min_cutoff", 0.5)
        beta = new_config.get("beta", 0.01)
        d_c = new_config.get("d_cutoff", 1.0)

        for f in [
            self.ui_pose_filter,
            self.ui_face_filter,
            self.ui_lh_filter,
            self.ui_rh_filter,
            self.world_pose_filter,
            self.world_face_filter,
            self.world_lh_filter,
            self.world_rh_filter,
            self.global_root_filter,
        ]:
            f.update_params(min_c, beta, d_c)
        print(f"[Vision] Filter params updated: min_cutoff={min_c}, beta={beta}")

    def _solve_head_pnp(self, face_landmarks):
        if not self.current_config.get("enable_head_pnp", True):
            return 0.0, 0.0, 0.0

        img_w, img_h = self.screen_width, self.screen_height

        image_points = np.array(
            [
                (
                    face_landmarks.landmark[1].x * img_w,
                    face_landmarks.landmark[1].y * img_h,
                ),
                (
                    face_landmarks.landmark[152].x * img_w,
                    face_landmarks.landmark[152].y * img_h,
                ),
                (
                    face_landmarks.landmark[33].x * img_w,
                    face_landmarks.landmark[33].y * img_h,
                ),
                (
                    face_landmarks.landmark[263].x * img_w,
                    face_landmarks.landmark[263].y * img_h,
                ),
                (
                    face_landmarks.landmark[61].x * img_w,
                    face_landmarks.landmark[61].y * img_h,
                ),
                (
                    face_landmarks.landmark[291].x * img_w,
                    face_landmarks.landmark[291].y * img_h,
                ),
            ],
            dtype=np.float64,
        )

        focal_length = self.screen_width
        center = (self.screen_width / 2, self.screen_height / 2)
        camera_matrix = np.array(
            [[focal_length, 0, center[0]], [0, focal_length, center[1]], [0, 0, 1]],
            dtype=np.float64,
        )

        dist_coeffs = np.zeros((4, 1), dtype=np.float64)

        success, rvec, tvec = cv2.solvePnP(
            FACE_3D_MODEL_POINTS,
            image_points,
            camera_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )

        if not success:
            return 0.0, 0.0, 0.0

        rmat, _ = cv2.Rodrigues(rvec)

        sy = math.sqrt(rmat[0, 0] * rmat[0, 0] + rmat[1, 0] * rmat[1, 0])
        singular = sy < 1e-6

        if not singular:
            x = math.atan2(rmat[2, 1], rmat[2, 2])
            y = math.atan2(-rmat[2, 0], sy)
            z = math.atan2(rmat[1, 0], rmat[0, 0])
        else:
            x = math.atan2(-rmat[1, 2], rmat[1, 1])
            y = math.atan2(-rmat[2, 0], sy)
            z = 0

        pitch = math.degrees(x)
        yaw = math.degrees(y)
        roll = math.degrees(z)

        smoothed_head = self.head_pose_filter.process([(pitch, yaw, roll)], time.time())
        if not smoothed_head:
            return pitch, yaw, roll

        s_p, s_y, s_r = smoothed_head[0]
        return s_p, s_y, s_r

    def _estimate_global_root(self, pose_landmarks):
        if not self.current_config.get("enable_global_depth", True):
            return 0.0, 0.0, 0.0

        import math

        l_shoulder = pose_landmarks.landmark[11]
        r_shoulder = pose_landmarks.landmark[12]

        dx = l_shoulder.x - r_shoulder.x
        dy = l_shoulder.y - r_shoulder.y
        norm_width = math.sqrt(dx * dx + dy * dy)

        if norm_width < 0.01:
            return 0.0, 0.0, 0.0

        pixel_width = norm_width * self.screen_width

        ref_width_m = self.current_config.get("ref_shoulder_width_m", 0.40)
        focal_length = self.current_config.get("camera_focal_length_px", 800.0)

        estimated_z = (ref_width_m * focal_length) / pixel_width

        mid_hip_x = (
            pose_landmarks.landmark[23].x + pose_landmarks.landmark[24].x
        ) / 2.0
        mid_hip_y = (
            pose_landmarks.landmark[23].y + pose_landmarks.landmark[24].y
        ) / 2.0

        offset_x = estimated_z * (mid_hip_x - 0.5) * self.screen_width / focal_length
        offset_y = estimated_z * (mid_hip_y - 0.5) * self.screen_height / focal_length

        smoothed_root = self.global_root_filter.process(
            [(offset_x, offset_y, estimated_z)], time.time()
        )
        if not smoothed_root:
            return 0.0, 0.0, 0.0

        s_x, s_y, s_z = smoothed_root[0]
        return s_x, s_y, s_z

    def _process_landmarks(
        self, landmarks, filter_manager, is_world=False, global_offset=(0.0, 0.0, 0.0)
    ):
        if not landmarks:
            return []
        current_t = time.time()
        raw_points = []
        visibility_list = []

        gx, gy, gz = global_offset

        for lm in landmarks.landmark:
            if is_world:
                # 叠加全局物理坐标偏移量
                raw_points.append((lm.x + gx, lm.y + gy, lm.z + gz))
                visibility_list.append(getattr(lm, "visibility", 1.0))
            else:
                raw_points.append((lm.x, lm.y, getattr(lm, "z", 0.0)))

        smoothed = filter_manager.process(raw_points, current_t)

        if is_world:
            flip_x = self.current_config.get("flip_x", False)
            flip_y = self.current_config.get("flip_y", False)
            flip_z = self.current_config.get("flip_z", False)
            res = []
            for i, (x_hat, y_hat, z_hat) in enumerate(smoothed):
                res.append(
                    {
                        "id": i,
                        "x": -x_hat if flip_x else x_hat,
                        "y": -y_hat if flip_y else y_hat,
                        "z": -z_hat if flip_z else z_hat,
                        "visibility": visibility_list[i],
                    }
                )
            return res
        else:
            res = []
            for x_hat, y_hat, _ in smoothed:
                res.append(
                    QPointF(x_hat * self.screen_width, y_hat * self.screen_height)
                )
            return res

    def run(self):
        input_mode = self.current_config.get("input_mode", "camera")
        video_path = self.current_config.get("video_path", "")
        camera_index = self.current_config.get("camera_index", 0)
        video_loop = self.current_config.get("video_loop", True)

        is_video_mode = input_mode == "video"

        if is_video_mode:
            if not os.path.exists(video_path):
                print(f"[Error] 视频文件未找到: {video_path}")
                return
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0:
                fps = 30.0
            frame_delay = 1.0 / fps
            print(f"[Vision] Video-to-Motion 开启: {video_path} (FPS: {fps:.1f})")
        else:
            cap = cv2.VideoCapture(camera_index)
            frame_delay = 0
            print("[Vision] Camera 实时捕捉开启")

        with self.mp_holistic.Holistic(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=False,
            enable_segmentation=False,
            refine_face_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        ) as holistic:
            while self._is_running and cap.isOpened():
                loop_start_time = time.time()

                success, image = cap.read()
                if not success:
                    if is_video_mode and video_loop:
                        print("[Vision] 视频循环重置...")
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        # 循环重置时清空历史状态，防止瞬间拉扯
                        for f in [
                            self.ui_pose_filter,
                            self.ui_face_filter,
                            self.ui_lh_filter,
                            self.ui_rh_filter,
                            self.world_pose_filter,
                            self.world_face_filter,
                            self.world_lh_filter,
                            self.world_rh_filter,
                        ]:
                            f.reset()
                        continue
                    elif is_video_mode and not video_loop:
                        print("[Vision] 视频处理完毕。")
                        break
                    else:
                        time.sleep(0.01)
                        continue

                image.flags.writeable = False
                if not is_video_mode:
                    image = cv2.flip(image, 1)  # 相机模式翻转
                image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

                results = holistic.process(image)

                ui_data = {"pose": [], "face": [], "left_hand": [], "right_hand": []}
                world_data = {"pose": [], "face": [], "left_hand": [], "right_hand": []}
                has_data = False

                if results.pose_landmarks:
                    has_data = True
                    global_root_offset = self._estimate_global_root(
                        results.pose_landmarks
                    )

                    ui_data["pose"] = self._process_landmarks(
                        results.pose_landmarks, self.ui_pose_filter, is_world=False
                    )
                    if results.pose_world_landmarks:
                        world_data["pose"] = self._process_landmarks(
                            results.pose_world_landmarks,
                            self.world_pose_filter,
                            is_world=True,
                            global_offset=global_root_offset,
                        )
                else:
                    self.ui_pose_filter.reset()
                    self.world_pose_filter.reset()
                    self.global_root_filter.reset()

                if results.face_landmarks:
                    ui_data["face"] = self._process_landmarks(
                        results.face_landmarks, self.ui_face_filter, is_world=False
                    )
                    world_data["face"] = self._process_landmarks(
                        results.face_landmarks, self.world_face_filter, is_world=True
                    )
                else:
                    self.ui_face_filter.reset()
                    self.world_face_filter.reset()

                if results.left_hand_landmarks:
                    ui_data["left_hand"] = self._process_landmarks(
                        results.left_hand_landmarks, self.ui_lh_filter, is_world=False
                    )
                    world_data["left_hand"] = self._process_landmarks(
                        results.left_hand_landmarks, self.world_lh_filter, is_world=True
                    )
                else:
                    self.ui_lh_filter.reset()
                    self.world_lh_filter.reset()

                if results.right_hand_landmarks:
                    ui_data["right_hand"] = self._process_landmarks(
                        results.right_hand_landmarks, self.ui_rh_filter, is_world=False
                    )
                    world_data["right_hand"] = self._process_landmarks(
                        results.right_hand_landmarks,
                        self.world_rh_filter,
                        is_world=True,
                    )
                else:
                    self.ui_rh_filter.reset()
                    self.world_rh_filter.reset()

                if has_data:
                    self.sig_pose_data_updated.emit(ui_data)
                    self.sig_3d_data_ready.emit(world_data)
                else:
                    self.sig_pose_data_updated.emit({})

                # FPS Sync for Video Mode
                if is_video_mode:
                    process_time = time.time() - loop_start_time
                    sleep_time = frame_delay - process_time
                    if sleep_time > 0:
                        time.sleep(sleep_time)

        cap.release()

    def stop(self):
        self._is_running = False
        self.wait()
