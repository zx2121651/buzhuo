import cv2
import time
import os
import math
import numpy as np
import mediapipe as mp
from PySide6.QtCore import QThread, Signal, QPointF
from one_euro_filter import PoseFilterManager
from modules.kalman_filter import KalmanPoseFilterManager

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
        kf_pn = conf.get("kalman_process_noise", 0.01)
        kf_mn = conf.get("kalman_measurement_noise", 0.1)
        self.ui_kalman_filter = KalmanPoseFilterManager(4, kf_pn, kf_mn)
        self.world_kalman_filter = KalmanPoseFilterManager(4, kf_pn, kf_mn)
        self.kalman_indices = [15, 16, 27, 28]

        # 专门用于平滑面部 Blendshapes 权重 (JawOpen, Smile, EyeBlinkLeft, EyeBlinkRight)
        self.blendshape_filter = PoseFilterManager(4, min_c, beta, d_c)

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

    def _solve_blendshapes(self, face_landmarks):
        """
        面部 Blendshapes 基础解算器。
        通过计算面部特定网格点之间的相对距离（并且通过归一化面部尺寸来保证尺度不变性），
        量化出 JawOpen (张嘴)、Smile (微笑)、EyeBlinkLeft (左眼眨眼)、EyeBlinkRight (右眼眨眼) 的权重值 (0~1)。
        """
        if not self.current_config.get("enable_face_blendshapes", True):
            return {
                "JawOpen": 0.0,
                "Smile": 0.0,
                "EyeBlinkLeft": 0.0,
                "EyeBlinkRight": 0.0,
            }

        import math

        lm = face_landmarks.landmark

        # 辅助函数：计算两点间的欧氏距离
        def dist(p1, p2):
            dx = lm[p1].x - lm[p2].x
            dy = lm[p1].y - lm[p2].y
            dz = lm[p1].z - lm[p2].z
            return math.sqrt(dx * dx + dy * dy + dz * dz)

        # 1. 提取面部尺度参考值 (Scale Invariant)
        face_height = dist(10, 152)  # 额头到下巴的距离
        face_width = dist(234, 454)  # 左右耳根的距离
        if face_height < 1e-4 or face_width < 1e-4:
            return {
                "JawOpen": 0.0,
                "Smile": 0.0,
                "EyeBlinkLeft": 0.0,
                "EyeBlinkRight": 0.0,
            }

        # 2. 计算 JawOpen (张嘴)
        # 上嘴唇内部中点(13) 到 下嘴唇内部中点(14) 的距离
        mouth_open = dist(13, 14) / face_height
        # 阈值映射: 0.01 是闭嘴, 0.1 是大张嘴
        jaw_open_weight = np.clip((mouth_open - 0.01) / (0.1 - 0.01), 0.0, 1.0)

        # 3. 计算 Smile (微笑)
        # 左右嘴角(61, 291) 的距离
        mouth_width = dist(61, 291) / face_width
        # 阈值映射: 0.35 是正常脸, 0.45 是大笑
        smile_weight = np.clip((mouth_width - 0.35) / (0.45 - 0.35), 0.0, 1.0)

        # 4. 计算 EyeBlinkLeft & EyeBlinkRight (眨眼)
        # 左眼上下眼睑距离 (159 到 145)
        left_eye_open = dist(159, 145) / face_height
        # 右眼上下眼睑距离 (386 到 374) (注意在镜像画面中左右的相对定义)
        right_eye_open = dist(386, 374) / face_height

        # 阈值映射: 0.02 认为眼睛是闭着的(权重1.0), 0.04 认为是睁开的(权重0.0)
        # 注意眨眼的逻辑是反过来的：距离越小，眨眼权重越大！
        blink_left_weight = 1.0 - np.clip(
            (left_eye_open - 0.02) / (0.04 - 0.02), 0.0, 1.0
        )
        blink_right_weight = 1.0 - np.clip(
            (right_eye_open - 0.02) / (0.04 - 0.02), 0.0, 1.0
        )

        # 5. 使用专用的 1€ Filter 平滑表情权重防抽搐
        # 这里我们将这 4 个标量包装成 4 个点的伪坐标，仅利用 x 轴传递数据
        raw_weights = [
            (jaw_open_weight, 0, 0),
            (smile_weight, 0, 0),
            (blink_left_weight, 0, 0),
            (blink_right_weight, 0, 0),
        ]
        smoothed_weights = self.blendshape_filter.process(raw_weights, time.time())
        if not smoothed_weights:
            return {
                "JawOpen": 0.0,
                "Smile": 0.0,
                "EyeBlinkLeft": 0.0,
                "EyeBlinkRight": 0.0,
            }

        return {
            "JawOpen": float(smoothed_weights[0][0]),
            "Smile": float(smoothed_weights[1][0]),
            "EyeBlinkLeft": float(smoothed_weights[2][0]),
            "EyeBlinkRight": float(smoothed_weights[3][0]),
        }

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
