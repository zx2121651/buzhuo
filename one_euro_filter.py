import math


class OneEuroFilter:
    """
    一维 1€ 滤波器 (One Euro Filter) 实现
    参考论文: http://www.lifl.fr/~casiez/1euro/
    """

    def __init__(self, min_cutoff=1.0, beta=0.0, d_cutoff=1.0):
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)

        # 历史状态
        self.x_prev = None
        self.dx_prev = None
        self.t_prev = None

    def __call__(self, x, t):
        """
        计算给定时间 t 的平滑值 x
        """
        if self.t_prev is None:
            # 第一次调用，没有历史状态，直接返回当前值并初始化状态
            self.x_prev = float(x)
            self.dx_prev = 0.0
            self.t_prev = float(t)
            return self.x_prev

        # 计算时间间隔 dte
        dte = t - self.t_prev

        if dte <= 0.0:
            # 避免除零或时间倒流
            return self.x_prev

        # 根据截止频率计算 alpha 的平滑因子
        def alpha(cutoff):
            tau = 1.0 / (2 * math.pi * cutoff)
            return 1.0 / (1.0 + tau / dte)

        # 根据位置差分计算当前速度 dx
        dx = (x - self.x_prev) / dte
        # 对速度进行低通平滑 (使用固定的 d_cutoff 截止频率)
        dx_hat = self._exponential_smoothing(alpha(self.d_cutoff), dx, self.dx_prev)

        # 根据平滑后的速度 dx_hat 计算当前的截止频率 cutoff
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)

        # 使用动态 cutoff 计算位置平滑因子 alpha，对当前位置 x 进行平滑
        x_hat = self._exponential_smoothing(alpha(cutoff), x, self.x_prev)

        # 更新历史状态
        self.x_prev = x_hat
        self.dx_prev = dx_hat
        self.t_prev = t

        return x_hat

    def _exponential_smoothing(self, a, x, x_prev):
        return a * x + (1 - a) * x_prev

    def reset(self):
        """
        重置滤波器的历史状态，用于目标丢失或重新追踪时
        """
        self.x_prev = None
        self.dx_prev = None
        self.t_prev = None


class PoseFilterManager:
    """
    全身姿态滤波器管理器
    用于同时管理 33 个关节点的 (X, Y, Z) 坐标，共 99 个独立的一维滤波器。
    """

    def __init__(self, num_points=33, min_cutoff=1.0, beta=0.0, d_cutoff=1.0):
        self.num_points = num_points
        # 创建 X, Y, Z 轴的滤波器列表
        self.filters_x = [
            OneEuroFilter(min_cutoff, beta, d_cutoff) for _ in range(num_points)
        ]
        self.filters_y = [
            OneEuroFilter(min_cutoff, beta, d_cutoff) for _ in range(num_points)
        ]
        self.filters_z = [
            OneEuroFilter(min_cutoff, beta, d_cutoff) for _ in range(num_points)
        ]

    def process(self, points, t):
        """
        处理一帧关节点坐标列表
        :param points: [(x0, y0, z0), (x1, y1, z1), ..., (x32, y32, z32)] 列表
        :param t: 当前系统时间戳 (秒)
        :return: 平滑后的 [(x0_hat, y0_hat, z0_hat), ...] 列表
        """
        # 如果输入的点数不是预期的，可能存在异常，不予处理
        if not points or len(points) != self.num_points:
            return points

        smoothed_points = []
        # 遍历每一个点并应用相应的滤波器
        for i, (x, y, z) in enumerate(points):
            x_hat = self.filters_x[i](x, t)
            y_hat = self.filters_y[i](y, t)
            z_hat = self.filters_z[i](z, t)
            smoothed_points.append((x_hat, y_hat, z_hat))
        return smoothed_points

    def reset(self):
        """
        清空所有 99 个滤波器的状态（例如在丢失目标追踪时调用）
        """
        for fx in self.filters_x:
            fx.reset()
        for fy in self.filters_y:
            fy.reset()
        for fz in self.filters_z:
            fz.reset()
