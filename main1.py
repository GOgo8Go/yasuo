import customtkinter as ctk
import os
import json
import subprocess
import threading
import queue
import re
import sys
import time
from tkinterdnd2 import DND_FILES, TkinterDnD
from tkinter import filedialog

# ────────────────────────────────────────────────
# 全局配置
# ────────────────────────────────────────────────
GAP = 8
ITEM_GAP = 5
FONT_MAIN = ("Microsoft YaHei", 15)
FONT_BOLD = ("Microsoft YaHei", 15, "bold")
FONT_INFO = ("Consolas", 14)

PRIMARY_ACTIVE = "#334155"
ACTIVE_TEXT = "#93c5fd"
BG_MAIN = "#0f172a"
BORDER_COLOR = "#475569"
COLOR_GRID = "#1e293b"
TEXT_COLOR = "#cbd5e1"
LABEL_COLOR = "#94a3b8"
INPUT_COLOR = "#10b981"
BTN_CLEAR_COLOR = "#f87171"
BTN_START_COLOR = "#34d399"
BTN_START_BORDER = "#059669"

CW = [60, 240, 420, 280, 80]
info_queue = queue.Queue()


class SlateButton(ctk.CTkButton):
    def __init__(self, master, text, is_selected=False, command=None, **kwargs):
        self.mode = kwargs.pop("mode", "normal")
        kwargs.setdefault("corner_radius", 6)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("font", FONT_MAIN)
        super().__init__(master, text=text, command=self._on_click, **kwargs)
        self.is_selected = is_selected
        self.external_command = command
        self.update_style()

    def _on_click(self):
        if self.external_command:
            self.external_command()

    def select(self):
        if not self.is_selected:
            self.is_selected = True
            self.update_style()

    def deselect(self):
        if self.is_selected:
            self.is_selected = False
            self.update_style()

    def update_style(self):
        if self.is_selected:
            self.configure(fg_color=PRIMARY_ACTIVE, border_color="#64748b", text_color=ACTIVE_TEXT)
        else:
            self.configure(fg_color="transparent", border_color=BORDER_COLOR, text_color=TEXT_COLOR)
        if self.mode == "clear":
            self.configure(text_color=BTN_CLEAR_COLOR)
        if self.mode == "start":
            self.configure(text_color=BTN_START_COLOR, border_color=BTN_START_BORDER)


class TaskRow(ctk.CTkFrame):
    def __init__(self, master, index, path, remove_cb):
        super().__init__(master, fg_color="transparent", height=55, corner_radius=0)
        self.pack_propagate(False)
        self.path = path
        self.duration = 0
        self.width = 0
        self.height = 0
        self.output_full_path = ""
        self.last_update_time = 0

        self.idx_cell = self._add_col(CW[0], str(index), "center", FONT_MAIN, "#475569")
        self._v_sep()
        self.name_cell = self._add_col(CW[1], os.path.basename(path), "w", FONT_MAIN, "#cbd5e1", padx=15)
        self._v_sep()
        self.info_cell = self._add_col(CW[2], "读取中...", "center", FONT_INFO, "#64748b")
        self._v_sep()

        self.p_box = ctk.CTkFrame(self, width=CW[3], fg_color="transparent")
        self.p_box.pack_propagate(False)
        self.p_box.pack(side="left", fill="y")
        self.pbar = ctk.CTkProgressBar(self.p_box, width=160, height=8, progress_color="#3b82f6", fg_color="#020617")
        self.pbar.set(0.0)
        self.pbar.place(relx=0.35, rely=0.5, anchor="center")
        self.p_text = ctk.CTkLabel(self.p_box, text="等待", font=FONT_INFO, text_color="#475569", width=60, cursor="hand2")
        self.p_text.place(relx=0.82, rely=0.5, anchor="center")
        self.p_text.bind("<Button-1>", lambda e: self.open_folder())
        self._v_sep()

        self.btn_box = ctk.CTkFrame(self, width=CW[4], fg_color="transparent")
        self.btn_box.pack_propagate(False)
        self.btn_box.pack(side="right", fill="y")
        self.del_btn = ctk.CTkButton(
            self.btn_box, text="✕", width=35, height=30, fg_color="transparent",
            hover_color="#ef4444", text_color="#475569", font=FONT_BOLD,
            command=lambda: remove_cb(path, self)
        )
        self.del_btn.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkFrame(self, height=1, fg_color=COLOR_GRID).place(relx=0, rely=1, relwidth=1, y=-1)
        info_queue.put((self, path))

    def update_index(self, new_idx):
        self.idx_cell.configure(text=str(new_idx))

    def update_status(self, progress, status_text=None, color=None, force=False):
        now = time.time()
        if not force and now - self.last_update_time < 0.1:
            return
        self.last_update_time = now
        self.pbar.set(progress / 100)
        if status_text:
            self.p_text.configure(text=status_text)
        else:
            self.p_text.configure(text=f"{int(progress)}%")
        if color:
            self.p_text.configure(text_color=color)

    def open_folder(self):
        target = self.output_full_path if self.output_full_path else self.path
        folder = os.path.dirname(target)
        if os.path.exists(folder):
            if sys.platform == "win32":
                os.startfile(folder)
            else:
                subprocess.Popen(["open", folder])

    def _add_col(self, w, txt, anchor, font, color, padx=0):
        cell = ctk.CTkFrame(self, width=w, fg_color="transparent", corner_radius=0)
        cell.pack_propagate(False)
        cell.pack(side="left", fill="y")
        lbl = ctk.CTkLabel(cell, text=txt, font=font, text_color=color, anchor=anchor, padx=padx)
        lbl.pack(fill="both", expand=True)
        return lbl

    def _v_sep(self):
        ctk.CTkFrame(self, width=1, fg_color=COLOR_GRID).pack(side="left", fill="y")


class VideoToolApp(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)
        self.title("PRO Video Processor")
        self.geometry("1180x720")
        self.configure(fg_color=BG_MAIN)

        self.selected_ratio = "9:16"
        self.selected_preset = "快 1080p30"
        self.custom_save_path = ""
        self.tasks = {}
        self.is_running = False
        self.last_config_snapshot = None

        self.setup_ui()
        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.on_drop)
        threading.Thread(target=self._info_worker, daemon=True).start()

    def setup_ui(self):
        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.pack(fill="x", padx=40, pady=(20, 20))  # 顶部和底部间距都设为 20

        # 第一行
        row_top = ctk.CTkFrame(ctrl, fg_color="transparent")
        row_top.pack(fill="x", pady=(0, GAP))

        g_ratio = ctk.CTkFrame(row_top, fg_color="transparent")
        g_ratio.pack(side="left")
        self._label(g_ratio, "目标比例").pack(side="left", padx=(0, ITEM_GAP))
        btn_916 = SlateButton(g_ratio, "9:16 (竖屏)", is_selected=True, command=lambda: self._switch_ratio("9:16"))
        btn_916.pack(side="left", padx=(0, ITEM_GAP))
        btn_169 = SlateButton(g_ratio, "16:9 (横屏)", command=lambda: self._switch_ratio("16:9"))
        btn_169.pack(side="left")
        self.ratio_btns = [btn_916, btn_169]

        g_preset = ctk.CTkFrame(row_top, fg_color="transparent")
        g_preset.pack(side="left", padx=GAP)
        self._label(g_preset, "预设").pack(side="left", padx=(0, ITEM_GAP))
        btn_ultrafast = SlateButton(g_preset, "极快 1080p30", command=lambda: self._switch_preset("极快 1080p30"))
        btn_ultrafast.pack(side="left", padx=(0, ITEM_GAP))
        btn_medium = SlateButton(g_preset, "快 1080p30", is_selected=True, command=lambda: self._switch_preset("快 1080p30"))
        btn_medium.pack(side="left")
        self.preset_btns = [btn_ultrafast, btn_medium]

        action_group = ctk.CTkFrame(row_top, fg_color="transparent")
        action_group.pack(side="right", anchor="e")
        SlateButton(action_group, "清空列表", mode="clear", command=self.clear_all).pack(side="left", padx=ITEM_GAP)
        self.save_btn = SlateButton(action_group, "保存位置", command=self.set_save_location)
        self.save_btn.pack(side="left", padx=ITEM_GAP)
        self.save_btn.bind("<Button-3>", lambda e: self.open_global_folder())
        self.start_btn = SlateButton(action_group, "开始转换", mode="start", command=self.start_conversion)
        self.start_btn.pack(side="left", padx=ITEM_GAP)

        # 第二行
        row = ctk.CTkFrame(ctrl, fg_color="transparent")
        row.pack(fill="x")

        params = [
            ("背景模糊", "blur", "80", self._bind_scroll_event, (1, 150)),
            ("旋转", "rotate", "0", self._bind_rotate_scroll, None),
            ("亮度", "brightness", "0", self._bind_scroll_event, (-100, 100)),
            ("对比度", "contrast", "1.0", self._bind_scroll_event, (0.5, 3.0, 0.1)),
            ("饱和度", "saturation", "1.0", self._bind_scroll_event, (0.0, 3.0, 0.1)),
            ("输出质量", "qual", "25", self._bind_scroll_event, (1, 51)),
            ("同时任务数", "concurrent", "2", None, None),
        ]

        for label, var_name, default, bind_func, bind_args in params:
            g = ctk.CTkFrame(row, fg_color="transparent")
            g.pack(side="left", padx=GAP)
            chk = ctk.CTkCheckBox(g, text="", width=16, height=16, command=self._on_param_changed) if var_name in ["blur", "rotate", "brightness", "contrast", "saturation"] else None
            if chk:
                chk.pack(side="left")
            self._label(g, label).pack(side="left", padx=ITEM_GAP)
            entry = self._entry(g, default)
            entry.pack(side="left")
            setattr(self, f"{var_name}_check", chk) if chk else None
            setattr(self, f"{var_name}_in", entry)
            if bind_func:
                if bind_args:
                    bind_func(entry, *bind_args)
                else:
                    bind_func(entry)

        # 同时任务数特殊处理
        self.concurrent_tasks_var = ctk.StringVar(value="2")
        self.concurrent_entry = self.concurrent_in
        def validate_concurrent(v):
            if v == "": return True
            try: return 1 <= int(v) <= 8
            except: return False
        self.concurrent_entry.configure(validate="key", validatecommand=(self.register(validate_concurrent), "%P"))
        def scroll_concurrent(e):
            try: v = int(self.concurrent_tasks_var.get() or "2")
            except: v = 2
            delta = 1 if e.delta > 0 else -1
            self.concurrent_tasks_var.set(str(max(1, min(8, v + delta))))
            self._on_param_changed()
        self.concurrent_entry.bind("<MouseWheel>", scroll_concurrent)

        # 失去焦点关闭光标闪烁
        for entry_name in ["blur_in", "rotate_in", "brightness_in", "contrast_in", "saturation_in", "qual_in", "concurrent_entry"]:
            entry = getattr(self, entry_name)
            entry.bind("<FocusOut>", lambda e, ent=entry: ent.configure(insertontime=0))
            entry.bind("<FocusIn>", lambda e, ent=entry: ent.configure(insertontime=600))

        # 表格区域
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=20, pady=(0, 25))

        self.table_box = ctk.CTkFrame(self.content_frame, fg_color="#111827", corner_radius=8, border_width=1, border_color=BORDER_COLOR)
        self.table_box.pack(fill="both", expand=True)

        self.header = ctk.CTkFrame(self.table_box, fg_color="#1e293b", height=45, corner_radius=0)
        self.header.pack(fill="x", padx=1, pady=(1, 0))
        self.header.pack_propagate(False)
        for i, t in enumerate(["序号", "文件名", "详细信息", "转换进度", "操作"]):
            side = "left" if i < 4 else "right"
            cell = ctk.CTkFrame(self.header, width=CW[i], fg_color="transparent")
            cell.pack_propagate(False)
            cell.pack(side=side, fill="y")
            ctk.CTkLabel(cell, text=t, font=FONT_BOLD, text_color="#cbd5e1").pack(fill="both", expand=True)
            if i < 3:
                ctk.CTkFrame(self.header, width=1, fg_color=COLOR_GRID).pack(side="left", fill="y")

        self.scroll = ctk.CTkScrollableFrame(self.table_box, fg_color="transparent", corner_radius=0)
        self.scroll.pack(fill="both", expand=True, padx=1, pady=1)

        self.update_idletasks()

    # ────────────────────────────────────────────────
    # 绑定方法
    # ────────────────────────────────────────────────

    def _bind_scroll_event(self, e_obj, min_v, max_v, step=1):
        def on_scroll(e):
            try:
                current = float(e_obj.get() or str(min_v if min_v > 0 else 0))
            except ValueError:
                current = min_v if min_v > 0 else 0
            delta = step if e.delta > 0 else -step
            new_value = max(min_v, min(max_v, current + delta))
            e_obj.delete(0, "end")
            if step < 1:
                e_obj.insert(0, f"{new_value:.1f}")
            else:
                e_obj.insert(0, str(int(new_value)))
            self._on_param_changed()
        e_obj.bind("<MouseWheel>", on_scroll)

    def _bind_rotate_scroll(self, e_obj):
        angles = ["90", "180", "270", "360"]
        def on_scroll(e):
            try:
                idx = angles.index(e_obj.get())
            except ValueError:
                idx = 0
            delta = 1 if e.delta > 0 else -1
            new_idx = (idx + delta) % 4
            e_obj.delete(0, "end")
            e_obj.insert(0, angles[new_idx])
            self._on_param_changed()
        e_obj.bind("<MouseWheel>", on_scroll)

    def _label(self, m, t):
        return ctk.CTkLabel(m, text=t, text_color=LABEL_COLOR, font=FONT_MAIN)

    def _entry(self, m, v=""):
        e = ctk.CTkEntry(
            m,
            width=58,
            height=34,
            fg_color="#0f172a",
            border_color=BORDER_COLOR,
            text_color=INPUT_COLOR,
            font=FONT_INFO,
            justify="center"
        )
        if v:
            e.insert(0, v)
        e.bind("<KeyRelease>", self._on_param_changed)
        return e

    # ────────────────────────────────────────────────
    # 核心功能（完整保留）
    # ────────────────────────────────────────────────

    def get_unique_path(self, dir_path, base_name, ext, mode_str):
        suffix = f"_{mode_str.replace(':', '_')}"
        candidate = os.path.join(dir_path, f"{base_name}{suffix}{ext}")
        if not os.path.exists(candidate):
            return candidate
        counter = 1
        while True:
            candidate = os.path.join(dir_path, f"{base_name}{suffix}_{counter}{ext}")
            if not os.path.exists(candidate):
                return candidate
            counter += 1

    def _run_ffmpeg(self, row, cfg):
        try:
            sigma = int(self.blur_in.get())
            crf = int(self.qual_in.get())
            rot_val = self.rotate_in.get()
            do_rotate = self.rotate_check.get()
            do_blur = self.blur_check.get()

            do_brightness = self.brightness_check.get()
            brightness = float(self.brightness_in.get()) / 100.0 if do_brightness else 0.0

            do_contrast = self.contrast_check.get()
            contrast = float(self.contrast_in.get()) if do_contrast else 1.0

            do_saturation = self.saturation_check.get()
            saturation = float(self.saturation_in.get()) if do_saturation else 1.0
        except Exception:
            sigma, crf, rot_val, do_rotate, do_blur = 80, 25, "90", False, False
            brightness, contrast, saturation = 0.0, 1.0, 1.0

        curr_w, curr_h = row.width, row.height
        if do_rotate and rot_val in ["90", "270"]:
            curr_w, curr_h = row.height, row.width

        is_target_v = cfg['mode'] == "9:16"
        tw, th = (1080, 1920) if is_target_v else (1920, 1080)
        needs_layout = abs((curr_w / curr_h) - (tw / th)) > 0.01

        vf_chain = []

        eq_parts = []
        if do_brightness:
            eq_parts.append(f"brightness={brightness:.2f}")
        if do_contrast:
            eq_parts.append(f"contrast={contrast:.2f}")
        if do_saturation:
            eq_parts.append(f"saturation={saturation:.2f}")
        if eq_parts:
            vf_chain.append("eq=" + ":".join(eq_parts))

        if do_rotate:
            if rot_val == "90": vf_chain.append("transpose=1")
            elif rot_val == "180": vf_chain.append("transpose=1,transpose=1")
            elif rot_val == "270": vf_chain.append("transpose=2")

        if needs_layout:
            if do_blur:
                blur_vf = f"split=2[main][bg];[bg]scale={'tw' if not is_target_v else '-1'}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},gblur=sigma={sigma}[bgblur];[main]scale={tw if is_target_v else '-2'}:{'-2' if is_target_v else th}:force_original_aspect_ratio=decrease[fg];[bgblur][fg]overlay=(W-w)/2:(H-h)/2"
                vf_chain.append(blur_vf.replace('tw', str(tw)))
            else:
                vf_chain.append(f"scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:black")
        else:
            vf_chain.append(f"scale={tw}:{th}")

        vf_chain.append("format=yuv420p")

        out_dir = self.custom_save_path if self.custom_save_path else os.path.dirname(row.path)
        base_n = os.path.splitext(os.path.basename(row.path))[0]
        out_path = self.get_unique_path(out_dir, base_n, ".mp4", cfg['mode'])
        row.output_full_path = out_path

        cmd = ['ffmpeg', '-y', '-i', row.path, '-vf', ",".join(vf_chain), '-c:v', 'libx264', '-preset', cfg['preset'], '-crf', str(crf), '-c:a', 'aac', out_path]

        try:
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True, encoding='utf-8', creationflags=0x08000000)
            pattern = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
            while True:
                line = process.stderr.readline()
                if not line: break
                match = pattern.search(line)
                if match and row.duration > 0:
                    h, m, s = map(float, match.groups())
                    p = min(int(((h*3600+m*60+s)/row.duration)*100), 99)
                    self.after(0, lambda val=p: row.update_status(val))
            process.wait()
            self.after(0, lambda: row.update_status(100, "✓ 完成", "#10b981", force=True) if process.returncode==0 else row.update_status(0, "失败", "#ef4444", force=True))
        except: self.after(0, lambda: row.update_status(0, "错误", "#ef4444", force=True))

    def _info_worker(self):
        while True:
            row, path = info_queue.get()
            try:
                cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,duration', '-of', 'json', path]
                res = json.loads(subprocess.check_output(cmd, creationflags=0x08000000).decode('utf-8'))
                if 'streams' in res and res['streams']:
                    s = res['streams'][0]
                    row.duration, row.width, row.height = float(s.get('duration', 0)), int(s['width']), int(s['height'])
                    size_mb = os.path.getsize(path) / (1024*1024)
                    info = f"{int(row.duration//60):02d}:{int(row.duration%60):02d} | {row.width}x{row.height} | {size_mb:.1f}MB"
                    self.after(0, lambda r=row, i=info: r.info_cell.configure(text=i))
            except: self.after(0, lambda r=row: r.info_cell.configure(text="解析失败"))
            finally: info_queue.task_done()

    def start_conversion(self):
        if self.is_running or not self.tasks:
            return

        self.last_config_snapshot = {
            "ratio": self.selected_ratio,
            "preset": self.selected_preset,
            "blur": self.blur_check.get(),
            "blur_v": self.blur_in.get(),
            "rot": self.rotate_check.get(),
            "rot_v": self.rotate_in.get(),
            "q": self.qual_in.get(),
            "concurrent": self.concurrent_tasks_var.get(),
            "brightness": self.brightness_check.get(),
            "brightness_v": self.brightness_in.get(),
            "contrast": self.contrast_check.get(),
            "contrast_v": self.contrast_in.get(),
            "saturation": self.saturation_check.get(),
            "saturation_v": self.saturation_in.get(),
            "tasks": len(self.tasks)
        }

        self.is_running = True
        self.start_btn.configure(state="disabled", fg_color="#334155", text_color="#93c5fd", text="转换中...")
        threading.Thread(target=self._run_all, daemon=True).start()

    def _run_all(self):
        try:
            max_workers = int(self.concurrent_tasks_var.get())
        except:
            max_workers = 2
        max_workers = max(1, min(8, max_workers))
        pool_sema = threading.Semaphore(max_workers)
        cfg = {'mode': self.selected_ratio, 'preset': 'ultrafast' if "极快" in self.selected_preset else 'medium'}
        rows = [r for r in self.scroll.winfo_children() if isinstance(r, TaskRow)]
        threads = []
        for r in rows:
            t = threading.Thread(target=lambda x=r: (pool_sema.acquire(), self._run_ffmpeg(x, cfg), pool_sema.release()))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        self.is_running = False
        self.after(0, self._update_start_button_state)
        self.after(0, lambda: rows[-1].open_folder() if rows else None)

    def _update_start_button_state(self):
        cur = {
            "ratio": self.selected_ratio,
            "preset": self.selected_preset,
            "blur": self.blur_check.get(),
            "blur_v": self.blur_in.get(),
            "rot": self.rotate_check.get(),
            "rot_v": self.rotate_in.get(),
            "q": self.qual_in.get(),
            "concurrent": self.concurrent_tasks_var.get(),
            "brightness": self.brightness_check.get(),
            "brightness_v": self.brightness_in.get() if self.brightness_check.get() else "0",
            "contrast": self.contrast_check.get(),
            "contrast_v": self.contrast_in.get() if self.contrast_check.get() else "1.0",
            "saturation": self.saturation_check.get(),
            "saturation_v": self.saturation_in.get() if self.saturation_check.get() else "1.0",
            "tasks": len(self.tasks)
        }

        if self.last_config_snapshot == cur:
            self.start_btn.configure(state="normal", fg_color="#334155", text_color="#93c5fd", text="开始转换")
        else:
            self.start_btn.configure(state="normal", fg_color="#059669", text_color="#e0f2fe", text="开始转换")

    def set_save_location(self):
        path = filedialog.askdirectory(title="选择保存位置")
        if path:
            self.custom_save_path = os.path.normpath(path)
            self.save_btn.configure(text_color="#93c5fd")
            self._on_param_changed()

    def open_global_folder(self):
        p = self.custom_save_path if self.custom_save_path else (os.path.dirname(list(self.tasks.keys())[0]) if self.tasks else "")
        if p and os.path.exists(p):
            if sys.platform == "win32":
                os.startfile(p)
            else:
                subprocess.Popen(["open", p])

    def _switch_ratio(self, v):
        self.selected_ratio = v
        for b in self.ratio_btns:
            b.select() if b.cget("text").startswith(v.split(":")[0]) else b.deselect()
        self._on_param_changed()

    def _switch_preset(self, v):
        self.selected_preset = v
        for b in self.preset_btns:
            b.select() if b.cget("text") == v else b.deselect()
        self._on_param_changed()

    def _on_param_changed(self, *args):
        if self.is_running:
            return

        self._update_start_button_state()

    def on_drop(self, event):
        for f in self.tk.splitlist(event.data):
            f = os.path.normpath(f)
            if f.lower().endswith(('.mp4', '.mov', '.mkv', '.avi', '.ts')) and f not in self.tasks:
                row = TaskRow(self.scroll, len(self.tasks)+1, f, self.remove_task)
                row.pack(fill="x")
                self.tasks[f] = row
        self._on_param_changed()

    def remove_task(self, p, w):
        if not self.is_running:
            w.destroy()
            self.tasks.pop(p, None)
            [r.update_index(i) for i, r in enumerate([x for x in self.scroll.winfo_children() if isinstance(x, TaskRow)], 1)]
            self._on_param_changed()

    def clear_all(self):
        if not self.is_running:
            [w.destroy() for w in self.scroll.winfo_children()]
            self.tasks.clear()
            self.last_config_snapshot = None
            self._on_param_changed()


if __name__ == "__main__":
    app = VideoToolApp()
    app.mainloop()
