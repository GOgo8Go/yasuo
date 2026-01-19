# main.py
import sys
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtCore import QThreadPool, Qt
import os

from ui import UIHandler


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(os.cpu_count())
        self.ui = UIHandler(self, self.pool)  # 传入 self 作为 parent

    # 拖拽事件必须放在 MainWindow
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        # 直接调用 UIHandler 的 drop 处理逻辑
        self.ui.dropEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    # PySide6 推荐直接使用 exec()
    sys.exit(app.exec())
