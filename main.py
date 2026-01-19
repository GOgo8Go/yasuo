# main.py
import sys
import os
import customtkinter as ctk
from ui import UIHandler

class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()

        # 1. 窗口基本设置
        self.title("视频比例转换器")
        self.geometry("1020x750")
        
        # 2. 设置图标 (逻辑增强：防止找不到文件报错)
        icon_path = "app_logo.ico"
        if getattr(sys, 'frozen', False):
            # 打包后的路径
            icon_path = os.path.join(sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable), icon_path)
        
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass # 某些系统不支持 iconbitmap 时静默跳过

        # 3. 初始化线程池模拟 (CTk 模式下主要靠 threading，这里保留引用以兼容 UI 逻辑)
        self.pool = None 

        # 4. 初始化 UI 处理器
        self.ui = UIHandler(self, self.pool)

        # 5. 绑定退出事件 (确保关闭窗口时结束所有子进程)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        # 可以在这里添加清理逻辑
        self.destroy()
        sys.exit(0)

if __name__ == "__main__":
    # 初始化 App
    app = MainWindow()
    
    # 启动主循环
    app.mainloop()
