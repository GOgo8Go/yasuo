import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import subprocess
import sys
import json
from threading import Thread

# 设置外观
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class ToastOverlay:
    """CTk 版浮动通知"""
    def __init__(self, parent):
        self.parent = parent
        self.label = None

    def show_msg(self, text="🎉 转换已全部完成"):
        if self.label: self.label.destroy()
        
        self.label = ctk.CTkLabel(
            self.parent, text=text,
            fg_color="#2a6e3c", text_color="white",
            corner_radius=10, font=("Microsoft YaHei", 16, "bold"),
            width=300, height=50
        )
        # 居中放置
        self.label.place(relx=0.5, rely=0.5, anchor="center")
        # 2秒后消失
        self.parent.after(2000, self.label.destroy)

class UIHandler:
    def __init__(self, parent_window, pool):
        self.parent = parent_window  # 这里的 parent 是 ctk.CTk 实例
        self.pool = pool
        self.cards = {}
        self.output_dir = None
        self.converting_count = 0
        self.config_file = "user_settings.json"
        
        # 预览图池在 CTk 环境下通常建议使用简单的线程管理，这里保留 pool 引用
        self.parent.thumb_pool = pool 

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        self.parent.title("视频转比例工具 (Lite版)")
        self.parent.geometry("980x720")
        
        # CTk 的布局容器
        self.main_container = ctk.CTkFrame(self.parent, fg_color="#0e1117")
        self.main_container.pack(fill="both", expand=True, padx=20, pady=20)

        # --- 顶部控制栏 ---
        self.top_bar = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.top_bar.pack(fill="x", pady=(0, 16))

        # 比例选择
        ctk.CTkLabel(self.top_bar, text="目标比例:").pack(side="left", padx=5)
        self.mode = ctk.CTkOptionMenu(self.top_bar, values=["9:16（竖屏）", "16:9（横屏）"], 
                                      command=self.on_param_changed_wrapper, width=140)
        self.mode.pack(side="left", padx=5)

        # 预设选择
        ctk.CTkLabel(self.top_bar, text="预设:").pack(side="left", padx=(15, 5))
        self.preset = ctk.CTkOptionMenu(self.top_bar, values=["ultrafast 1080p30", "fast 1080p30", "自定义"],
                                        command=self.on_param_changed_wrapper, width=160)
        self.preset.pack(side="left", padx=5)

        # 模糊开关
        self.blur_var = ctk.BooleanVar()
        self.blur_check = ctk.CTkCheckBox(self.top_bar, text="背景模糊", variable=self.blur_var,
                                          command=self.on_blur_changed)
        self.blur_check.pack(side="left", padx=(15, 5))

        # 模糊强度
        ctk.CTkLabel(self.top_bar, text="强度:").pack(side="left", padx=5)
        self.blur_input = ctk.CTkEntry(self.top_bar, width=45)
        self.blur_input.insert(0, "60")
        self.blur_input.pack(side="left", padx=5)
        self.blur_input.bind("<KeyRelease>", self.on_param_changed_wrapper)

        # 质量 (CRF)
        ctk.CTkLabel(self.top_bar, text="质量:").pack(side="left", padx=(15, 5))
        self.quality_input = ctk.CTkEntry(self.top_bar, width=45)
        self.quality_input.insert(0, "25")
        self.quality_input.pack(side="left", padx=5)
        self.quality_input.bind("<KeyRelease>", self.on_param_changed_wrapper)

        # 右侧按钮组
        self.start_btn = ctk.CTkButton(self.top_bar, text="开始转换", fg_color="#2a6e3c", 
                                       hover_color="#3a8e50", command=self.start_all, width=100)
        self.start_btn.pack(side="right", padx=5)

        self.folder_btn = ctk.CTkButton(self.top_bar, text="输出目录", fg_color="#3a4048", 
                                        state="disabled", command=self.open_folder, width=100)
        self.folder_btn.pack(side="right", padx=5)

        self.clear_btn = ctk.CTkButton(self.top_bar, text="清空列表", fg_color="#334155", 
                                       hover_color="#ef4444", command=self.clear_list, width=100)
        self.clear_btn.pack(side="right", padx=5)

        # --- 中央列表区 ---
        self.area_container = ctk.CTkFrame(self.main_container, fg_color="#111827", 
                                           border_width=2, border_color="#334155")
        self.area_container.pack(fill="both", expand=True)

        # 上传提示区
        self.upload_hint = ctk.CTkFrame(self.area_container, fg_color="transparent")
        self.upload_hint.place(relx=0.5, rely=0.5, anchor="center")
        
        self.plus_btn = ctk.CTkButton(self.upload_hint, text="+", width=80, height=80, 
                                      corner_radius=40, font=("Arial", 60), command=self.select_files)
        self.plus_btn.pack(pady=10)
        
        self.hint_text = ctk.CTkLabel(self.upload_hint, text="点击加号上传或使用系统对话框选择\n支持 mp4, mov, mkv, avi, flv",
                                      text_color="#64748b", font=("Microsoft YaHei", 14))
        self.hint_text.pack()

        # 滚动列表区 (CTkScrollableFrame 非常强大)
        self.scroll_frame = ctk.CTkScrollableFrame(self.area_container, fg_color="transparent")
        
        # Toast 提示组件
        self.toast = ToastOverlay(self.area_container)

    # --- 逻辑适配层 ---

    def on_param_changed_wrapper(self, *args):
        self.on_param_changed()
        self.save_settings()

    def on_param_changed(self):
        for card in self.cards.values():
            if hasattr(card, 'status'):
                card.status.configure(text="等待", text_color="#94a3b8")
                card.pbar.set(0)
                card.percent.configure(text="0%")

    def on_blur_changed(self):
        if self.blur_var.get():
            self.blur_input.configure(state="normal")
        else:
            self.blur_input.configure(state="disabled")
        self.on_param_changed_wrapper()

    def select_files(self):
        files = filedialog.askopenfilenames(title="选择视频文件", 
                                            filetypes=[("Video Files", "*.mp4 *.mov *.mkv *.avi *.flv")])
        if files: self.process_files(list(files))

    def process_files(self, files):
        if not files: return
        self.upload_hint.place_forget()
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        from core import VideoCard
        for path in files:
            if path not in self.cards:
                # 注意：VideoCard 类在 core.py 中也需要适配 CTkFrame
                card = VideoCard(self.scroll_frame, path, self.remove_card)
                card.pack(fill="x", pady=5)
                self.cards[path] = card
                if not self.output_dir: self.output_dir = os.path.dirname(path)
                self.folder_btn.configure(state="normal")

    def remove_card(self, path, widget):
        if path in self.cards:
            del self.cards[path]
            widget.destroy()
            if not self.cards:
                self.folder_btn.configure(state="disabled")
                self.scroll_frame.pack_forget()
                self.upload_hint.place(relx=0.5, rely=0.5, anchor="center")

    def clear_list(self):
        for path in list(self.cards.keys()):
            self.remove_card(path, self.cards[path])

    def start_all(self):
        targets = [c for c in self.cards.values() if "等待" in c.status.cget("text")]
        if not targets: return
        
        self.start_btn.configure(state="disabled", text="转换中...")
        self.converting_count = len(targets)
        
        config = {
            "mode": "9:16" if "9:16" in self.mode.get() else "16:9",
            "blur": self.blur_var.get(),
            "blur_sigma": int(self.blur_input.get() or 60),
            "crf": int(self.quality_input.get() or 25),
            "preset": 'ultrafast' if "ultrafast" in self.preset.get() else 'fast'
        }
        
        from core import VideoWorker
        for path, card in list(self.cards.items()):
            if card not in targets: continue
            card.status.configure(text="处理中...", text_color="#4a9eff")
            
            # 适配信号：由于 CTk 没有 PyQt 的 Signal，VideoWorker 需要改用回调
            w = VideoWorker(path, config, card.duration)
            # 注入回调逻辑 (需要在 core.py 配合修改)
            w.on_progress = lambda v, c=card: c.update_progress(v)
            w.on_finished = lambda out, c=card: self.on_ok(c)
            w.on_error = lambda msg, c=card: self.on_fail(c, msg)
            
            # 使用池或线程启动
            Thread(target=w.run, daemon=True).start()

    def on_ok(self, card):
        self.converting_count -= 1
        self.parent.after(0, self.check_finish)

    def on_fail(self, card, msg):
        self.converting_count -= 1
        self.parent.after(0, self.check_finish)

    def check_finish(self):
        if self.converting_count <= 0:
            self.start_btn.configure(state="normal", text="开始转换")
            self.toast.show_msg()

    def open_folder(self):
        target = os.path.join(self.output_dir, "Converted_Videos")
        if not os.path.exists(target): target = self.output_dir
        if sys.platform == "win32": os.startfile(target)
        else: subprocess.call(["open", target])

    def save_settings(self):
        try:
            settings = {
                "mode_index": self.mode.get(),
                "preset_index": self.preset.get(),
                "blur_checked": self.blur_var.get(),
                "blur_sigma": self.blur_input.get(),
                "crf": self.quality_input.get()
            }
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
        except: pass

    def load_settings(self):
        if not os.path.exists(self.config_file): return
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                s = json.load(f)
                self.mode.set(s.get("mode_index", "9:16（竖屏）"))
                self.preset.set(s.get("preset_index", "ultrafast 1080p30"))
                self.blur_var.set(s.get("blur_checked", False))
                self.on_blur_changed()
                self.blur_input.delete(0, "end")
                self.blur_input.insert(0, s.get("blur_sigma", "60"))
                self.quality_input.delete(0, "end")
                self.quality_input.insert(0, s.get("crf", "25"))
        except: pass

    # 拖拽功能在 Tkinter 中需要额外的集成 (如 windnd)，建议先用加号上传
    def dropEvent(self, event):
        pass
