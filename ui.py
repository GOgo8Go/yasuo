from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
import os
import subprocess
import sys
import json

# 注入：系统通知组件 (操作区上层居中)
class ToastOverlay(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.label = QLabel("🎉 转换已全部完成", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("""
            background-color: rgba(42, 110, 60, 0.95);
            color: white;
            font-size: 18px;
            font-weight: bold;
            padding: 15px 35px;
            border-radius: 10px;
            border: 1px solid #3a8e50;
        """)
        self.hide()
        
    def show_msg(self):
        self.resize(self.parent().size())
        self.label.adjustSize()
        lx = (self.width() - self.label.width()) // 2
        ly = (self.height() - self.label.height()) // 2
        self.label.move(lx, ly)
        self.show()
        self.raise_()
        QTimer.singleShot(2000, self.hide)

class UIHandler:
    def __init__(self, parent_window, pool):
        self.parent = parent_window
        self.pool = pool
        self.cards = {}
        self.output_dir = None
        self.converting_count = 0
        self.config_file = "user_settings.json"
        
        # 性能优化：初始化预览图专用池
        self.parent.thumb_pool = QThreadPool()
        self.parent.thumb_pool.setMaxThreadCount(3)

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        self.parent.setWindowTitle("视频转比例工具")
        self.parent.resize(980, 720)
        self.parent.setAcceptDrops(True)

        self.parent.setStyleSheet("""
            QMainWindow {background:#0e1117;}
            QLabel {color:#ddd; font-size:16px;}
            QCheckBox {color:#ddd; font-size:16px;}
            QComboBox {background:#1f2329; color:#eee; border:1px solid #333; border-radius:4px; padding:4px; font-size:16px;}
            QLineEdit {background:#1f2329; color:#eee; border:1px solid #333; border-radius:4px; padding:4px; font-size:16px;}
            QLineEdit:disabled {background:#2a2a2a; color:#888;}
            QPushButton#start {background:#2a6e3c; color:white; border:none; border-radius:6px; padding:8px 16px; font-weight:bold; font-size:16px;}
            QPushButton#start:hover {background:#3a8e50;}
            QPushButton#start:disabled {background:#1a2e1c; color:#888;}
            QPushButton#folder {background:#3a4048; color:#ccc; border:1px solid #555; padding:6px 16px; font-size:16px;}
            QPushButton#folder:hover {background:#4a5058;}
            QPushButton#clear {background:#334155; color:#cbd5e1; border:none; border-radius:6px; padding:8px 16px; font-size:14px;}
            QPushButton#clear:hover {background:#ef4444; color:white;}
        """)

        central = QWidget()
        self.parent.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        top = QHBoxLayout()
        top.setSpacing(8)

        top.addWidget(QLabel("目标比例:"))
        self.mode = QComboBox()
        self.mode.addItems(["9:16（竖屏）", "16:9（横屏）"])
        self.mode.currentIndexChanged.connect(self.on_param_changed)
        self.mode.currentIndexChanged.connect(self.save_settings)
        top.addWidget(self.mode)

        top.addSpacing(15)
        top.addWidget(QLabel("预设:"))
        self.preset = QComboBox()
        self.preset.addItems(["ultrafast 1080p30", "fast 1080p30", "自定义"])
        self.preset.currentIndexChanged.connect(self.on_param_changed)
        self.preset.currentIndexChanged.connect(self.save_settings)
        top.addWidget(self.preset)

        top.addSpacing(15)
        self.blur = QCheckBox("背景模糊")
        self.blur.stateChanged.connect(self.on_blur_changed)
        self.blur.stateChanged.connect(self.on_param_changed)
        self.blur.stateChanged.connect(self.save_settings)
        top.addWidget(self.blur)

        top.addWidget(QLabel("强度:"))
        # 完善范围限制：模糊 0-100
        self.blur_input = NumberInput("60", self.on_param_changed, 0, 100)
        self.blur_input.setFixedWidth(45)
        self.blur_input.setEnabled(False)
        self.blur_input.textChanged.connect(self.on_param_changed)
        self.blur_input.textChanged.connect(self.save_settings)
        top.addWidget(self.blur_input)

        top.addSpacing(15)
        top.addWidget(QLabel("输出质量:"))
        # 完善范围限制：CRF 0-51
        self.quality_input = NumberInput("25", self.on_param_changed, 0, 51)
        self.quality_input.setFixedWidth(45)
        self.quality_input.textChanged.connect(self.on_param_changed)
        self.quality_input.textChanged.connect(self.save_settings)
        top.addWidget(self.quality_input)

        top.addStretch(1)

        # 交互优化：新增“清空列表”
        self.clear_btn = QPushButton("清空列表")
        self.clear_btn.setObjectName("clear")
        self.clear_btn.clicked.connect(self.clear_list)
        top.addWidget(self.clear_btn)

        self.folder_btn = QPushButton("输出目录")
        self.folder_btn.setObjectName("folder")
        self.folder_btn.clicked.connect(self.open_folder)
        self.folder_btn.setEnabled(False)
        top.addWidget(self.folder_btn)

        self.start_btn = QPushButton("开始转换")
        self.start_btn.setObjectName("start")
        self.start_btn.clicked.connect(self.start_all)
        top.addWidget(self.start_btn)
        
        layout.addLayout(top)

        self.area_container = QWidget()
        self.area_container.setObjectName("areaContainer")
        self.area_container.setStyleSheet("QWidget#areaContainer { border: 2px dashed #334155; border-radius: 12px; background: #111827; }")
        area_layout = QVBoxLayout(self.area_container)
        area_layout.setContentsMargins(0, 0, 0, 0)

        self.upload_hint = QWidget()
        hint_layout = QVBoxLayout(self.upload_hint)
        hint_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plus_btn = QPushButton("+")
        self.plus_btn.setFixedSize(80, 80)
        self.plus_btn.setStyleSheet("QPushButton { background: #1f2937; color: #6366f1; border: 2px solid #312e81; border-radius: 40px; font-size: 60px; font-weight: bold; padding-bottom: 8px; text-align: center; } QPushButton:hover { background: #312e81; color: white; }")
        self.plus_btn.clicked.connect(self.select_files)
        hint_layout.addWidget(self.plus_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        self.hint_text = QLabel("拖拽视频到此处，或点击加号上传\n支持 mp4, mov, mkv, avi, flv\n（支持批量上传）")
        self.hint_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_text.setStyleSheet("color:#64748b; font-size:16px; margin-top:10px; border:none; background:transparent;")
        hint_layout.addWidget(self.hint_text)
        area_layout.addWidget(self.upload_hint)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("border:none; background:transparent;")
        self.content = QWidget()
        self.card_layout = QVBoxLayout(self.content)
        self.card_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.card_layout.setContentsMargins(15, 15, 15, 15)
        self.card_layout.setSpacing(12)
        self.scroll.setWidget(self.content)
        self.scroll.hide()
        area_layout.addWidget(self.scroll)
        layout.addWidget(self.area_container)

        # 注入：浮动通知层
        self.toast = ToastOverlay(self.area_container)

    def clear_list(self):
        for path in list(self.cards.keys()):
            self.remove_card(path, self.cards[path])

    def save_settings(self):
        settings = {"mode_index": self.mode.currentIndex(), "preset_index": self.preset.currentIndex(), "blur_checked": self.blur.isChecked(), "blur_sigma": self.blur_input.text(), "crf": self.quality_input.text()}
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f: json.dump(settings, f, indent=4)
        except: pass

    def load_settings(self):
        if not os.path.exists(self.config_file): return
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                s = json.load(f)
                self.mode.blockSignals(True); self.mode.setCurrentIndex(s.get("mode_index", 0)); self.mode.blockSignals(False)
                self.preset.blockSignals(True); self.preset.setCurrentIndex(s.get("preset_index", 0)); self.preset.blockSignals(False)
                self.blur.blockSignals(True); self.blur.setChecked(s.get("blur_checked", False)); self.blur.blockSignals(False)
                self.blur_input.setEnabled(self.blur.isChecked())
                self.blur_input.setText(s.get("blur_sigma", "60"))
                self.quality_input.setText(s.get("crf", "25"))
        except: pass

    def on_param_changed(self, *args):
        for card in self.cards.values():
            if "完成" in card.status.text() or "失败" in card.status.text():
                card.status.setText("等待"); card.status.setStyleSheet("font-size:14px; color:#94a3b8;")
                card.pbar.setValue(0); card.percent.setText("0%")

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(self.parent, "选择视频文件", "", "Video Files (*.mp4 *.mov *.mkv *.avi *.flv)")
        if files: self.process_files(files)

    def process_files(self, files):
        if not files: return
        self.upload_hint.hide(); self.scroll.show()
        for path in files:
            if path not in self.cards:
                from core import VideoCard
                card = VideoCard(path, self.remove_card)
                self.card_layout.addWidget(card); self.cards[path] = card
                if not self.output_dir: self.output_dir = os.path.dirname(path)
                self.folder_btn.setEnabled(True)

    def on_blur_changed(self, state):
        self.blur_input.setEnabled(state == Qt.CheckState.Checked.value)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.accept()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        valid_files = [p for p in paths if p.lower().endswith(('.mp4','.mov','.mkv','.avi','.flv'))]
        if valid_files: self.process_files(valid_files)

    def remove_card(self, path, widget):
        if path in self.cards:
            del self.cards[path]; widget.deleteLater()
            if not self.cards: self.folder_btn.setEnabled(False); self.scroll.hide(); self.upload_hint.show()

    def start_all(self):
        targets = [c for c in self.cards.values() if "等待" in c.status.text()]
        if not targets: return
        self.start_btn.setEnabled(False); self.start_btn.setText("转换中...")
        self.converting_count = len(targets)
        config = {"mode": "9:16" if "9:16" in self.mode.currentText() else "16:9", "blur": self.blur.isChecked(), 
                  "blur_sigma": int(self.blur_input.text() or 60), "crf": int(self.quality_input.text() or 25), 
                  "preset": 'ultrafast' if "ultrafast" in self.preset.currentText() else 'fast'}
        from core import VideoWorker
        for path, card in list(self.cards.items()):
            if card not in targets: continue
            card.status.setText("处理中..."); card.status.setStyleSheet("color:#4a9eff;")
            w = VideoWorker(path, config, card.duration)
            w.signals.progress.connect(lambda p, v, c=card: c.update_progress(v))
            w.signals.finished.connect(lambda out, c=card: self.on_ok(c))
            w.signals.error.connect(lambda p, msg, c=card: self.on_fail(c, msg))
            self.pool.start(w)

    def on_ok(self, card):
        self.converting_count -= 1
        self.check_finish()

    def on_fail(self, card, msg):
        self.converting_count -= 1
        self.check_finish()

    def check_finish(self):
        if self.converting_count <= 0:
            self.start_btn.setEnabled(True); self.start_btn.setText("开始转换")
            # 注入：2秒自动关闭通知
            self.toast.show_msg()

    def open_folder(self):
        target = os.path.join(self.output_dir, "Converted_Videos")
        if not os.path.exists(target): target = self.output_dir
        if sys.platform == "win32": os.startfile(target)
        else: subprocess.call(["open", target])

class NumberInput(QLineEdit):
    def __init__(self, default_value, callback, min_v=0, max_v=100):
        super().__init__(str(default_value))
        self.callback = callback
        self.min_v = min_v
        self.max_v = max_v
        # 注入：输入限制校验
        self.textChanged.connect(self._validate)

    def _validate(self):
        text = self.text()
        if not text: return
        try:
            val = int(text)
            if val < self.min_v: self.setText(str(self.min_v))
            elif val > self.max_v: self.setText(str(self.max_v))
            self.callback()
        except: self.setText(str(self.min_v))

    def wheelEvent(self, event):
        if self.isEnabled():
            delta = 1 if event.angleDelta().y() > 0 else -1
            try:
                val = int(self.text())
                new_val = max(self.min_v, min(self.max_v, val + delta))
                self.blockSignals(True)
                self.setText(str(new_val))
                self.blockSignals(False)
                self.callback()
                self.textChanged.emit(self.text())
            except: pass
            event.accept()