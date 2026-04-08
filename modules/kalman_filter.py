import cv2
import numpy as np


class Kalman3DFilter:
    """
    一维独立的 3D 卡尔曼滤波器。
    用于对单独的一个关节点进行位置(X,Y,Z)和速度(dX,dY,dZ)的物理惯性预测与平滑更新。
    系统状态矩阵尺寸为 6 (x,y,z,dx,dy,dz)，测量矩阵尺寸为 3 (x,y,z)。
    """

    def __init__(self, process_noise=0.01, measurement_noise=0.1):
        self.kf = cv2.KalmanFilter(6, 3)
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise
        self.last_t = None

        # 1. 测量矩阵 (Measurement Matrix H)
        # 观测方程: Z = H * X
        # 我们只能观测到位置 (x,y,z)，看不到速度 (dx,dy,dz)
        self.kf.measurementMatrix = np.array(
            [[1, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0], [0, 0, 1, 0, 0, 0]], np.float32
        )

        # 2. 状态转移矩阵 (Transition Matrix F)
        # 运动学方程: X(t) = X(t-1) + V(t-1) * dt
        # 这个矩阵的 dt 我们会在每一次 process() 时根据实际帧间隔更新
        self.kf.transitionMatrix = np.array(
            [
                [1, 0, 0, 1, 0, 0],  # x = x + dt*dx
                [0, 1, 0, 0, 1, 0],  # y = y + dt*dy
                [0, 0, 1, 0, 0, 1],  # z = z + dt*dz
                [0, 0, 0, 1, 0, 0],  # dx = dx (假设匀速模型)
                [0, 0, 0, 0, 1, 0],  # dy = dy
                [0, 0, 0, 0, 0, 1],  # dz = dz
            ],
            np.float32,
        )

        # 3. 过程噪声协方差矩阵 (Process Noise Covariance Q)
        # 物理模型的不确定度。值越小，越相信匀速运动模型（平滑，预测强）；值越大，越相信外部不可控力量的突变（容易抖）。
        self.kf.processNoiseCov = np.eye(6, dtype=np.float32) * self.process_noise

        # 4. 测量噪声协方差矩阵 (Measurement Noise Covariance R)
        # 摄像头/MediaPipe的抖动程度。值越大，越不相信传进来的坐标（平滑）；值越小，越贴近传进来的原始坐标（抖动）。
        self.kf.measurementNoiseCov = (
            np.eye(3, dtype=np.float32) * self.measurement_noise
        )

        # 初始误差协方差矩阵 (Error Covariance P)
        self.kf.errorCovPost = np.eye(6, dtype=np.float32) * 1.0

    def process(self, x, y, z, t):
        if self.last_t is None:
            # 第一次调用，初始化状态变量
            self.kf.statePost = np.array(
                [[x], [y], [z], [0], [0], [0]], dtype=np.float32
            )
            self.last_t = t
            return (x, y, z)

        dt = t - self.last_t
        if dt <= 0:
            dt = 0.001

        # 动态更新转移矩阵中的时间间隔 dt
        self.kf.transitionMatrix[0, 3] = dt
        self.kf.transitionMatrix[1, 4] = dt
        self.kf.transitionMatrix[2, 5] = dt

        # 1. 物理预测阶段 (Predict)
        # 基于上一帧的位置和速度，预测当前这一帧它由于惯性应该飞到了哪里
        _ = self.kf.predict()

        # 2. 测量更新阶段 (Correct / Update)
        # 摄像头送来了 MediaPipe 算出的最新真实位置
        measurement = np.array([[np.float32(x)], [np.float32(y)], [np.float32(z)]])

        # 卡尔曼根据之前配置好的 Q 和 R 噪声系数，智能融合预测值和测量值，给出最合理的最新状态
        estimated = self.kf.correct(measurement)

        self.last_t = t

        # 提取融合后的平滑位置
        s_x, s_y, s_z = estimated[0, 0], estimated[1, 0], estimated[2, 0]
        return (s_x, s_y, s_z)

    def reset(self):
        self.last_t = None
        self.kf.statePost = np.zeros((6, 1), np.float32)
        self.kf.errorCovPost = np.eye(6, dtype=np.float32) * 1.0

    def update_params(self, process_noise, measurement_noise):
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise
        self.kf.processNoiseCov = np.eye(6, dtype=np.float32) * self.process_noise
        self.kf.measurementNoiseCov = (
            np.eye(3, dtype=np.float32) * self.measurement_noise
        )


class KalmanPoseFilterManager:
    """
    用于同时管理多个高动态 3D 关节点的卡尔曼滤波器。
    """

    def __init__(self, num_points, process_noise=0.01, measurement_noise=0.1):
        self.num_points = num_points
        self.filters = [
            Kalman3DFilter(process_noise, measurement_noise) for _ in range(num_points)
        ]

    def process(self, points, t):
        if not points or len(points) != self.num_points:
            return points

        smoothed_points = []
        for i, (x, y, z) in enumerate(points):
            smoothed_points.append(self.filters[i].process(x, y, z, t))
        return smoothed_points

    def reset(self):
        for f in self.filters:
            f.reset()

    def update_params(self, process_noise, measurement_noise):
        for f in self.filters:
            f.update_params(process_noise, measurement_noise)
