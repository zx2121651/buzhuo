# 动捕动画软件画布

这是一个基于 PySide6 的透明、置顶且点击穿透的桌面全屏窗口应用。此应用作为动捕动画软件的画布，主要运行在 Windows 系统上。

## 进阶功能
- **全局快捷键**：
  - 按下 `Insert` 键可切换画布的显示与隐藏。
  - 按下 `End` 键可安全退出整个应用程序。
- **全身动捕实时绘制 (Full Body Pose)**：
  - 接入了 OpenCV 和 MediaPipe Pose，实现了对摄像头的实时全身关键点（33个关节点）追踪。
  - 画面已做镜像翻转处理，您的动作将以类似光标或镜面反射的方式，直接按比例拉伸并投射到整个全屏画布上。
  - 在全透明的屏幕上，您将看到实时的全身骨架（青色连线、红色关节点），头部有黄色高亮圆圈，以及左右手食指指尖的蓝色光标效果。

## 环境配置

1. 确保已安装 Python 3.8 或以上版本。
2. 确保您的电脑连接了摄像头。
3. 创建并激活虚拟环境：
   *在 Windows 系统上：*
   `python -m venv venv`
   `venv\Scripts\activate`

   *在 macOS/Linux 系统上：*
   `python -m venv venv`
   `source venv/bin/activate`
4. 安装依赖：
   `pip install -r requirements.txt`

*(注意：在某些系统下，`keyboard` 库的全局按键钩子可能需要管理员/root权限)*

## 运行程序

在激活虚拟环境的情况下，执行以下命令：
`python main.py`
