import os
import subprocess
import json
import random
import string
import sys
import re

from PyQt6.QtWidgets import QFrame, QLabel, QProgressBar, QPushButton, QHBoxLayout, QVBoxLayout, QApplication
from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, QTimer, Qt
from PyQt6.QtGui import QPixmap

# --- 新增：获取内置 FFmpeg 路径的逻辑 ---
def get_ffmpeg_exe():
    """如果是打包后的环境，从临时文件夹获取 exe，否则使用系统命令"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, "ffmpeg.exe")
    return "ffmpeg"

def get_ffprobe_exe():
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, "ffprobe.exe")
    return "ffprobe"
# ---------------------------------------

class WorkerSignals(QObject):
    progress = pyqtSignal(str, int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str, str)


class VideoWorker(QRunnable):
    def __init__(self, file_path, config, duration):
        super().__init__()
        self.file_path = file_path
        self.config = config
        self.duration = duration
        self.signals = WorkerSignals()

    def run(self):
        # 1. 创建子目录 Converted_Videos
        dir_name = os.path.dirname(self.file_path)
        out_dir = os.path.join(dir_name, "Converted_Videos")
        if not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(self.file_path))[0]
        suffix = "9-16" if self.config['mode'] == "9:16" else "16-9"
        
        # 2. 智能重命名逻辑
        output = os.path.join(out_dir, f"{base_name}_{suffix}.mp4")
        counter = 1
        while os.path.exists(output):
            output = os.path.join(out_dir, f"{base_name}_{suffix}_{counter}.mp4")
            counter += 1

        is_vertical = self.config['mode'] == "9:16"
        target_w, target_h = (1080, 1920) if is_vertical else (1920, 1080)

        if self.config.get('blur', False):
            sigma = self.config.get('blur_sigma', 60)
            if is_vertical:
                vf = (f"[0:v]split=2[main][bg];[bg]scale=-1:{target_h}:force_original_aspect_ratio=increase,"
                      f"crop={target_w}:{target_h},gblur=sigma={sigma}[bgblur];"
                      f"[main]scale={target_w}:-2:force_original_aspect_ratio=decrease[fg];"
                      f"[bgblur][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p")
            else:
                vf = (f"[0:v]split=2[main][bg];[bg]scale={target_w}:-1:force_original_aspect_ratio=increase,"
                      f"crop={target_w}:{target_h},gblur=sigma={sigma}[bgblur];"
                      f"[main]scale=-2:{target_h}:force_original_aspect_ratio=decrease[fg];"
                      f"[bgblur][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p")
        else:
            vf = (f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
                  f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p")

        # 3. 优化参数：兼容无音轨视频 (-map 0:v? -map 0:a?)
        cmd = [
            'ffmpeg', '-y', '-i', self.file_path,
            '-vf', vf,
            '-c:v', 'libx264',
            '-preset', self.config.get('preset', 'ultrafast'),
            '-crf', str(self.config.get('crf', 23)),
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '192k',
            '-map', '0:v?', '-map', '0:a?',
            '-threads', '0', output
        ]

        try:
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True, encoding='utf-8',
                                     creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            pattern = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
            while True:
                line = process.stderr.readline()
                if not line: break
                match = pattern.search(line)
                if match and self.duration > 0:
                    h, m, s = map(float, match.groups())
                    curr = h * 3600 + m * 60 + s
                    self.signals.progress.emit(self.file_path, min(int((curr / self.duration) * 100), 99))
            process.wait()
            if process.returncode == 0:
                self.signals.progress.emit(self.file_path, 100)
                self.signals.finished.emit(output)
            else:
                self.signals.error.emit(self.file_path, f"ffmpeg 返回码 {process.returncode}")
        except Exception as e:
            self.signals.error.emit(self.file_path, f"执行异常: {str(e)}")


class VideoCard(QFrame):
    def __init__(self, path, delete_callback):
        super().__init__()
        self.path = path
        self.duration = 0.0
        self.delete_callback = delete_callback
        self.setObjectName("videoCard")
        self.setFixedHeight(160)
        self.setStyleSheet("QFrame#videoCard { background: #17212f; border: 1px solid #334155; border-radius: 12px; }")

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(20)

        self.thumb = QLabel()
        self.thumb.setFixedSize(240, 135)
        self.thumb.setStyleSheet("background: #0f1620; border: 2px solid #1e2a3a; border-radius: 12px;")
        main_layout.addWidget(self.thumb)

        right_layout = QVBoxLayout()
        right_layout.setSpacing(12)

        self.name = QLabel(os.path.basename(path))
        self.name.setStyleSheet("font-size:16px; font-weight:bold; color:#e0e7ff;")
        right_layout.addWidget(self.name)

        self.info = QLabel("读取中...")
        self.info.setStyleSheet("font-size:14px; color:#94a3b8;")
        right_layout.addWidget(self.info)

        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(10)
        self.pbar = QProgressBar()
        self.pbar.setFixedHeight(12)
        self.pbar.setTextVisible(False)
        self.pbar.setStyleSheet("QProgressBar {background:#1e293b; border:none; border-radius:6px;} QProgressBar::chunk {background:#3b82f6; border-radius:6px;}")
        progress_layout.addWidget(self.pbar, 1)

        self.percent = QLabel("0%")
        self.percent.setStyleSheet("font-size:14px; font-weight:bold; color:#60a5fa; min-width:60px; text-align:right;")
        progress_layout.addWidget(self.percent)
        right_layout.addLayout(progress_layout)

        self.status = QLabel("等待")
        self.status.setStyleSheet("font-size:14px; color:#94a3b8; text-align:center;")
        right_layout.addWidget(self.status)

        main_layout.addLayout(right_layout, 1)

        self.delete_btn = QPushButton("×")
        self.delete_btn.setParent(self)
        self.delete_btn.setFixedSize(32, 32)
        self.delete_btn.setStyleSheet("QPushButton { background: rgba(239,68,68,0.8); color: white; border: none; border-radius: 16px; font-size: 18px; font-weight: bold; } QPushButton:hover { background: #ef4444; }")
        self.delete_btn.clicked.connect(self.on_delete)

        # 延迟加载，防止卡顿
        QTimer.singleShot(50, self.load_info)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.delete_btn.move(self.width() - 48, 12)

    def load_info(self):
        # 1. 尝试使用池来管理预览图任务（防止瞬间开启几十个进程）
        main_win = QApplication.activeWindow()
        if hasattr(main_win, 'thumb_pool'):
            main_win.thumb_pool.start(ThumbTask(self))
        else:
            self._do_load()

    def _do_load(self):
        """执行具体的读取逻辑（保留原始临时文件方式，确保能显示）"""
        try:
            cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', self.path]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', 
                                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            data = json.loads(result.stdout)
            video = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), None)
            if video:
                self.duration = float(data['format'].get('duration', 0))
                size_mb = os.path.getsize(self.path) / (1024**2)
                res = f"{video.get('width','?')}×{video.get('height','?')}"
                bitrate = int(data['format'].get('bit_rate', 0)) // 1000 if data['format'].get('bit_rate') else '未知'
                fps = video.get('r_frame_rate', '未知')
                self.info.setText(f"{int(self.duration // 60):02d}:{int(self.duration % 60):02d} 、{res} 、{bitrate}kbps 、{fps} 、{size_mb:.1f}M")

            # 抓取预览图逻辑 (保留原逻辑，确保生效)
            tmp = f"tmp_thumb_{random.randint(10000,99999)}.jpg"
            subprocess.run(['ffmpeg', '-y', '-i', self.path, '-ss', '1', '-vframes', '1', '-vf', 'scale=240:135', tmp], 
                           stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=="win32" else 0)
            if os.path.exists(tmp):
                pix = QPixmap(tmp)
                if not pix.isNull():
                    self.thumb.setPixmap(pix.scaled(240, 135, Qt.AspectRatioMode.KeepAspectRatio))
                os.remove(tmp)
        except:
            self.info.setText("读取失败")

    def on_delete(self):
        self.delete_callback(self.path, self)

    def update_progress(self, value):
        self.pbar.setValue(value)
        self.percent.setText(f"{value}%")
        if value >= 100:
            self.status.setText("✓ 完成")
            self.status.setStyleSheet("font-size:14px; color:#10b981;")

# 预览图信号量控制任务
class ThumbTask(QRunnable):
    def __init__(self, card):
        super().__init__()
        self.card = card
    def run(self):

        self.card._do_load()
