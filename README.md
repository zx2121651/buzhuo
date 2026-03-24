# 动捕动画软件画布

这是一个基于 PySide6 的透明、置顶且点击穿透的桌面全屏窗口应用。此应用作为动捕动画软件的画布，主要运行在 Windows 系统上。

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

## 运行程序

在激活虚拟环境的情况下，执行以下命令：
`python main.py`

程序运行后，您将看到屏幕中央有一个半透明的红色十字准星，并且边缘有半透明的红色边框。该窗口始终置顶且允许鼠标点击穿透到底层的应用程序。
