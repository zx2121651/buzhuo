# 动捕动画软件画布

这是一个基于 PySide6 的透明、置顶且点击穿透的桌面全屏窗口应用。此应用作为动捕动画软件的画布，主要运行在 Windows 系统上。

## 进阶功能
- **全局快捷键**：
  - 按下 `Insert` 键可切换画布的显示与隐藏。
  - 按下 `End` 键可安全退出整个应用程序。
- **动态绘制接口**：
  - 包含了一个模拟后台进程的 `QThread`，以约 60FPS 的频率生成随机坐标，并通过 PySide6 信号/槽机制无卡顿地将坐标传递给 UI 线程。
  - 画布上除固定的半透明边框外，还会渲染一个跟随这些模拟坐标实时移动的绿色准星和圆圈。

## 环境配置

1. 确保已安装 Python 3.8 或以上版本。
2. 创建并激活虚拟环境：
   *在 Windows 系统上：*
   `python -m venv venv`
   `venv\Scripts\activate`

   *在 macOS/Linux 系统上：*
   `python -m venv venv`
   `source venv/bin/activate`
3. 安装依赖：
   `pip install -r requirements.txt`

*(注意：在某些系统下，`keyboard` 库的全局按键钩子可能需要管理员/root权限)*

## 运行程序

在激活虚拟环境的情况下，执行以下命令：
`python main.py`
