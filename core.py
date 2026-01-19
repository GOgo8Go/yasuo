import os
import subprocess
import json
import random
import sys
import re
import threading
from PIL import Image, ImageTk # 需要安装: pip install pillow

import customtkinter as ctk

# --- 路径识别逻辑：确保打包后能找到 ffmpeg ---
def get_ffmpeg_exe():
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
        return os.path.join(base_path, "ffmpeg.exe")
    return 'ffmpeg'

def get_ffprobe_exe():
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
        return os.path.join(base_path, "ffprobe.exe")
    return 'ffprobe'

class VideoWorker:
    """处理视频转换的逻辑类 (普通 Python 类，不继承 QRunnable)"""
    def __init__(self, file_path, config, duration):
        self.file_path = file_path
        self.config = config
        self.duration = duration
        # 定义回调函数
        self.on_progress = None
        self.on_finished = None
        self.on_error = None

    def run(self):
        dir_name = os.path.dirname(self.file_path)
        out_dir = os.path.join(dir_name, "Converted_Videos")
        os.makedirs(out_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(self.file_path))[0]
        suffix = "9-16" if self.config['mode'] == "9:16" else "16-9"
        
        output = os.path.join(out_dir, f"{base_name}_{suffix}.mp4")
        counter = 1
        while os.path.exists(output):
            output = os.path.join(out_dir, f"{base_name}_{suffix}_{counter}.mp4")
            counter += 1

        is_vertical = self.config['mode'] == "9:16"
        target_w, target_h = (1080, 1920) if is_vertical else (1920, 1080)

        # 拼接滤镜链 (保持原逻辑不变)
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

        cmd = [
            get_ffmpeg_exe(), '-y', '-i', self.file_path,
            '-vf', vf, '-c:v', 'libx264',
            '-preset', self.config.get('preset', 'ultrafast'),
            '-crf', str(self.config.get('crf', 23)),
            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
            '-map', '0:v?', '-map', '0:a?', '-threads', '0', output
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
                    percent = min(int((curr / self.duration) * 100), 99)
                    if self.on_progress: self.on_progress(percent)
            
            process.wait()
            if process.returncode == 0:
                if self.on_progress: self.on_progress(100)
                if self.on_finished: self.on_finished(output)
            else:
                if self.on_error: self.on_error(f"FFmpeg Error {process.returncode}")
        except Exception as e:
            if self.on_error: self.on_error(str(e))


class VideoCard(ctk.CTkFrame):
    """适配 CustomTkinter 的列表项卡片"""
    def __init__(self, master, path, delete_callback):
        super().__init__(master, fg_color="#17212f", border_width=1, border_color="#334155", corner_radius=12)
        self.path = path
        self.duration = 0.0
        self.delete_callback = delete_callback

        # 布局配置
        self.grid_columnconfigure(1, weight=1)
        
        # 预览图 (使用 CTkLabel 承载)
        self.thumb_label = ctk.CTkLabel(self, text="预览加载中...", width=240, height=135, 
                                        fg_color="#0f1620", corner_radius=12)
        self.thumb_label.grid(row=0, column=0, padx=16, pady=16)

        # 右侧信息区
        self.info_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.info_frame.grid(row=0, column=1, sticky="nsew", pady=16)

        self.name = ctk.CTkLabel(self.info_frame, text=os.path.basename(path), 
                                 font=("Microsoft YaHei", 16, "bold"), text_color="#e0e7ff")
        self.name.pack(anchor="w")

        self.info = ctk.CTkLabel(self.info_frame, text="读取中...", font=("Microsoft YaHei", 13), text_color="#94a3b8")
        self.info.pack(anchor="w", pady=(2, 8))

        # 进度条
        self.pbar = ctk.CTkProgressBar(self.info_frame, height=12, fg_color="#1e293b", progress_color="#3b82f6")
        self.pbar.set(0)
        self.pbar.pack(fill="x", side="left", expand=True)

        self.percent = ctk.CTkLabel(self.info_frame, text="0%", font=("Arial", 13, "bold"), text_color="#60a5fa", width=50)
        self.percent.pack(side="right", padx=10)

        self.status = ctk.CTkLabel(self.info_frame, text="等待", font=("Microsoft YaHei", 13), text_color="#94a3b8")
        self.status.pack(side="bottom", anchor="w")

        # 删除按钮
        self.delete_btn = ctk.CTkButton(self, text="×", width=30, height=30, corner_radius=15,
                                        fg_color="#ef4444", hover_color="#dc2626",
                                        command=self.on_delete)
        self.delete_btn.place(relx=1.0, x=-40, y=12)

        # 开启线程加载视频信息
        threading.Thread(target=self.load_info, daemon=True).start()

    def load_info(self):
        try:
            # 1. 获取视频元数据
            cmd = [get_ffprobe_exe(), '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', self.path]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', 
                                   creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            data = json.loads(result.stdout)
            video = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), None)
            
            if video:
                self.duration = float(data['format'].get('duration', 0))
                size_mb = os.path.getsize(self.path) / (1024**2)
                res = f"{video.get('width','?')}×{video.get('height','?')}"
                self.info.configure(text=f"{int(self.duration // 60):02d}:{int(self.duration % 60):02d} | {res} | {size_mb:.1f}M")

            # 2. 提取预览图
            tmp_img = f"tmp_{random.randint(1000,9999)}.jpg"
            subprocess.run([get_ffmpeg_exe(), '-y', '-ss', '1', '-i', self.path, '-vframes', '1', '-vf', 'scale=240:135', tmp_img],
                           stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=="win32" else 0)
            
            if os.path.exists(tmp_img):
                img = Image.open(tmp_img)
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(240, 135))
                self.thumb_label.configure(image=ctk_img, text="")
                os.remove(tmp_img)
        except:
            self.info.configure(text="读取失败")

    def on_delete(self):
        self.delete_callback(self.path, self)

    def update_progress(self, value):
        # Tkinter 更新 UI 必须在主线程，由于 CustomTkinter 的底层处理，这里直接调用通常 OK
        self.pbar.set(value / 100)
        self.percent.configure(text=f"{value}%")
        if value >= 100:
            self.status.configure(text="✓ 完成", text_color="#10b981")
