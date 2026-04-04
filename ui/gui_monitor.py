# File: gui_monitor.py
import threading
import queue
import tkinter as tk
from tkinter import ttk
import time
import cv2
from PIL import Image, ImageTk
from utils.setup_log import setup_logger
from ui.state_proxy import StateProxy

logger = setup_logger("gui_monitor", "logs/gui_monitor/log")


class GUIMonitor:
    def __init__(
        self,
        api_client=None,
        state_manager=None,
        validate_pairs=None,
        shutdown_callback=None,
        camera_manager=None,
        camera_api_client=None,
        pairs_by_zone=None,
        cameras_config=None,
        camera_zones=None,
        rtsp_ae5=None,
        rtsp_ae6=None,
        rtsp_5l=None,
        rtsp_6l=None,
        rtsp_af=None,
    ):
        # Support both direct state_manager (old mode) and api_client (new mode)
        if api_client and not state_manager:
            self.state_manager = StateProxy(api_client)
            self.use_proxy = True
        else:
            self.state_manager = state_manager
            self.use_proxy = False
        
        self.validate_pairs = list(validate_pairs) if validate_pairs else []
        self.shutdown_callback = shutdown_callback
        self.camera_manager = camera_manager
        self.camera_api_client = camera_api_client
        self.pairs_by_zone = pairs_by_zone or {"AE5": [], "AE6": [], "AF": [], "5L": [], "6L": []}
        self.cameras_config = cameras_config or []
        self.camera_zones = camera_zones or []
        self.rtsp_ae5 = rtsp_ae5 if rtsp_ae5 is not None else set()
        self.rtsp_ae6 = rtsp_ae6 if rtsp_ae6 is not None else set()
        self.rtsp_5l = rtsp_5l if rtsp_5l is not None else set()
        self.rtsp_6l = rtsp_6l if rtsp_6l is not None else set()
        self.rtsp_af = rtsp_af if rtsp_af is not None else set()
        self._preview_windows = []

        self.window = tk.Tk()
        self.window.title("VALIDATE_PAIRS Monitor")
        self.window.geometry("1920x1080")
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)

        top = tk.Frame(self.window)
        top.pack(fill=tk.X, padx=5, pady=5)

        # Ưu tiên camera_api_client (new API-based approach), fallback camera_manager (old direct approach)
        camera_control = self.camera_api_client or self.camera_manager
        if camera_control:
            tk.Button(top, text="Start All", command=camera_control.start_all_cameras).pack(side=tk.LEFT, padx=2)
            tk.Button(top, text="Stop All", command=camera_control.stop_all_cameras).pack(side=tk.LEFT, padx=2)
            tk.Button(top, text="AE5 On", command=lambda: camera_control.set_zone_enabled("AE5", True)).pack(side=tk.LEFT, padx=2)
            tk.Button(top, text="AE5 Off", command=lambda: camera_control.set_zone_enabled("AE5", False)).pack(side=tk.LEFT, padx=2)
            tk.Button(top, text="AE6 On", command=lambda: camera_control.set_zone_enabled("AE6", True)).pack(side=tk.LEFT, padx=2)
            tk.Button(top, text="AE6 Off", command=lambda: camera_control.set_zone_enabled("AE6", False)).pack(side=tk.LEFT, padx=2)
            # tk.Button(top, text="5L On", command=lambda: self.camera_manager.set_zone_enabled("5L", True)).pack(side=tk.LEFT, padx=2)
            # tk.Button(top, text="5L Off", command=lambda: self.camera_manager.set_zone_enabled("5L", False)).pack(side=tk.LEFT, padx=2)
            # tk.Button(top, text="6L On", command=lambda: self.camera_manager.set_zone_enabled("6L", True)).pack(side=tk.LEFT, padx=2)
            # tk.Button(top, text="6L Off", command=lambda: self.camera_manager.set_zone_enabled("6L", False)).pack(side=tk.LEFT, padx=2)
            # tk.Button(top, text="AF On", command=lambda: self.camera_manager.set_zone_enabled("AF", True)).pack(side=tk.LEFT, padx=2)
            # tk.Button(top, text="AF Off", command=lambda: self.camera_manager.set_zone_enabled("AF", False)).pack(side=tk.LEFT, padx=2)

        # Khung Cameras trước đây có checkbox từng camera đã được bỏ,
        # chỉ sử dụng Start All / Stop All / AE5 / AE6 để điều khiển.

        main_frame = tk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=1)
        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable = tk.Frame(canvas)
        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.labels = []
        self.empty_start_labels = []  # Cột 3: chỉ start với len(pair)==1 trong VALIDATE_PAIRS
        pairs_ae5 = [p for p in self.pairs_by_zone.get("AE5", []) if len(p) == 2]
        pairs_ae6 = [p for p in self.pairs_by_zone.get("AE6", []) if len(p) == 2]
        empty_starts = [p[0] for p in self.validate_pairs if len(p) == 1]

        cols = ["Start", "St", "Flag", "Time", "Cam", "End", "St", "Flag", "Time", "Cam"]
        cols_empty = ["Start", "St", "Flag", "Time", "Cam"]
        col_span = len(cols)

        # Cột 1: AE5 (chỉ cặp 2 phần tử)
        left_frame = tk.LabelFrame(scrollable, text="AE5")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        for c, h in enumerate(cols):
            tk.Label(left_frame, text=h, font=("Arial", 9, "bold"), bg="#2c3e50", fg="white", padx=4, pady=2).grid(row=0, column=c, sticky="nsew")
        for idx, (start_point, end_point) in enumerate(pairs_ae5, start=1):
            self._add_pair_row(left_frame, idx, start_point, end_point)

        # Cột 2: AE6 (chỉ cặp 2 phần tử)
        right_frame = tk.LabelFrame(scrollable, text="AE6")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        for c, h in enumerate(cols):
            tk.Label(right_frame, text=h, font=("Arial", 9, "bold"), bg="#2c3e50", fg="white", padx=4, pady=2).grid(row=0, column=c, sticky="nsew")
        for idx, (start_point, end_point) in enumerate(pairs_ae6, start=1):
            self._add_pair_row(right_frame, idx, start_point, end_point)

        # Cột 3: Xe trống — chỉ các start với len(pair)==1 trong VALIDATE_PAIRS
        empty_frame = tk.LabelFrame(scrollable, text="Xe trống (start only)")
        empty_frame.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)
        for c, h in enumerate(cols_empty):
            tk.Label(empty_frame, text=h, font=("Arial", 9, "bold"), bg="#2c3e50", fg="white", padx=4, pady=2).grid(row=0, column=c, sticky="nsew")
        for idx, start_point in enumerate(empty_starts, start=1):
            self._add_empty_start_row(empty_frame, idx, start_point)

        # AF column
        # af_frame = tk.LabelFrame(scrollable, text="AF")
        # af_frame.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)
        # for c, h in enumerate(cols):
        #     tk.Label(af_frame, text=h, font=("Arial", 9, "bold"), bg="#2c3e50", fg="white", padx=4, pady=2).grid(row=0, column=c, sticky="nsew")
        # for idx, (start_point, end_point) in enumerate(pairs_af, start=1):
        #     self._add_pair_row(af_frame, idx, start_point, end_point)

        # # 5L + 6L (SUB) column
        # sub_frame = tk.LabelFrame(scrollable, text="5L + 6L")
        # sub_frame.grid(row=0, column=3, sticky="nsew", padx=5, pady=5)
        # for c, h in enumerate(cols):
        #     tk.Label(sub_frame, text=h, font=("Arial", 9, "bold"), bg="#2c3e50", fg="white", padx=4, pady=2).grid(row=0, column=c, sticky="nsew")
        # for idx, (start_point, end_point) in enumerate(pairs_sub, start=1):
        #     self._add_pair_row(sub_frame, idx, start_point, end_point)

        scrollable.grid_columnconfigure(0, weight=1)
        scrollable.grid_columnconfigure(1, weight=1)
        scrollable.grid_columnconfigure(2, weight=1)
        for col in range(col_span):
            left_frame.grid_columnconfigure(col, weight=1)
            right_frame.grid_columnconfigure(col, weight=1)
        for col in range(len(cols_empty)):
            empty_frame.grid_columnconfigure(col, weight=1)

    def _add_pair_row(self, parent, row_idx, start_point, end_point):
        row_labels = {}
        r = row_idx
        # Start
        tk.Label(parent, text=start_point[:18], font=("Arial", 8), relief="solid", padx=2, pady=2).grid(row=r, column=0, sticky="nsew")
        row_labels["start_state"] = tk.Label(parent, text="F", font=("Arial", 8), relief="solid", padx=2, pady=2)
        row_labels["start_state"].grid(row=r, column=1, sticky="nsew")
        row_labels["start_flag"] = tk.Button(parent, text="F", font=("Arial", 8), padx=2, pady=2, command=lambda sp=start_point: self.toggle_flag(sp, "start"))
        row_labels["start_flag"].grid(row=r, column=2, sticky="nsew")
        row_labels["start_time"] = tk.Label(parent, text="-", font=("Arial", 8), relief="solid", padx=2, pady=2)
        row_labels["start_time"].grid(row=r, column=3, sticky="nsew")
        row_labels["start_cam_btn"] = tk.Button(parent, text="Cam", font=("Arial", 8), padx=2, pady=2, command=lambda n=start_point: self._on_cam_button_click(n))
        row_labels["start_cam_btn"].grid(row=r, column=4, sticky="nsew")
        # End
        tk.Label(parent, text=end_point[:18], font=("Arial", 8), relief="solid", padx=2, pady=2).grid(row=r, column=5, sticky="nsew")
        row_labels["end_state"] = tk.Label(parent, text="F", font=("Arial", 8), relief="solid", padx=2, pady=2)
        row_labels["end_state"].grid(row=r, column=6, sticky="nsew")
        row_labels["end_flag"] = tk.Button(parent, text="F", font=("Arial", 8), padx=2, pady=2, command=lambda ep=end_point: self.toggle_flag(ep, "end"))
        row_labels["end_flag"].grid(row=r, column=7, sticky="nsew")
        row_labels["end_time"] = tk.Label(parent, text="-", font=("Arial", 8), relief="solid", padx=2, pady=2)
        row_labels["end_time"].grid(row=r, column=8, sticky="nsew")
        row_labels["end_cam_btn"] = tk.Button(parent, text="Cam", font=("Arial", 8), padx=2, pady=2, command=lambda n=end_point: self._on_cam_button_click(n))
        row_labels["end_cam_btn"].grid(row=r, column=9, sticky="nsew")
        # prog = ttk.Progressbar(parent, maximum=20, length=60)
        # prog.grid(row=r, column=10, sticky="nsew", padx=2)
        # row_labels["start_progress"] = prog
        # end_prog = ttk.Progressbar(parent, maximum=20, length=60)
        # row_labels["end_progress"] = end_prog
        # end_prog.grid(row=r, column=11, sticky="nsew", padx=2)
        self.labels.append({"start_point": start_point, "end_point": end_point, "labels": row_labels})

    def _add_empty_start_row(self, parent, row_idx, start_point):
        """Hàng chỉ start (xe trống, len(pair)==1): Start, St, Flag, Time, Cam."""
        row_labels = {}
        r = row_idx
        tk.Label(parent, text=start_point[:18], font=("Arial", 8), relief="solid", padx=2, pady=2).grid(row=r, column=0, sticky="nsew")
        row_labels["start_state"] = tk.Label(parent, text="F", font=("Arial", 8), relief="solid", padx=2, pady=2)
        row_labels["start_state"].grid(row=r, column=1, sticky="nsew")
        row_labels["start_flag"] = tk.Button(parent, text="F", font=("Arial", 8), padx=2, pady=2, command=lambda sp=start_point: self.toggle_flag(sp, "start"))
        row_labels["start_flag"].grid(row=r, column=2, sticky="nsew")
        row_labels["start_time"] = tk.Label(parent, text="-", font=("Arial", 8), relief="solid", padx=2, pady=2)
        row_labels["start_time"].grid(row=r, column=3, sticky="nsew")
        row_labels["start_cam_btn"] = tk.Button(parent, text="Cam", font=("Arial", 8), padx=2, pady=2, command=lambda n=start_point: self._on_cam_button_click(n))
        row_labels["start_cam_btn"].grid(row=r, column=4, sticky="nsew")
        self.empty_start_labels.append({"start_point": start_point, "labels": row_labels})

    def _on_camera_toggle(self, index, on):
        """Giữ lại cho tương thích, hiện không dùng checkbox camera."""
        if self.camera_manager:
            self.camera_manager.set_camera_enabled(index, on)

    def _get_roi_for_node(self, node_id):
        """Lấy ROI [x, y, w, h] cho node_id từ cameras_config. Trả về None nếu không có."""
        for cam in self.cameras_config:
            rois = cam.get("rois", [])
            if isinstance(rois, dict):
                for roi_key, roi_val in rois.items():
                    coords = roi_val.get("roi") if isinstance(roi_val, dict) else roi_val
                    roi_key_str = str(roi_key)

                    if roi_key_str.startswith("start_") or roi_key_str.startswith("end_"):
                        internal_node_id = roi_key_str
                    elif isinstance(roi_val, dict):
                        if bool(roi_val.get("start")):
                            internal_node_id = f"start_{roi_key_str}"
                        elif bool(roi_val.get("end")):
                            internal_node_id = f"end_{roi_key_str}"
                        else:
                            continue
                    else:
                        internal_node_id = roi_key_str

                    if internal_node_id == node_id:
                        return coords
            else:
                for roi_dict in rois:
                    if roi_dict.get("node_id") == node_id:
                        return roi_dict.get("roi")
        return None

    def _on_cam_button_click(self, node_id):
        """Khi bấm nút Cam: mở popup combobox chọn 1) Xem camera 2) Bật/Tắt camera."""
        if not self.camera_manager:
            return
        cam_id = self.camera_manager.get_cam_id_for_node(node_id)
        if cam_id is None:
            return
        popup = tk.Toplevel(self.window)
        popup.title(f"Cam — {node_id}")
        popup.geometry("280x100")
        popup.transient(self.window)
        tk.Label(popup, text="Chọn thao tác:", font=("Arial", 9)).pack(pady=(8, 4))
        choices = ["Xem camera", "Bật/Tắt camera"]
        combo = ttk.Combobox(popup, values=choices, state="readonly", width=20, font=("Arial", 9))
        combo.pack(pady=4)
        combo.set(choices[0])

        def run_and_close():
            sel = combo.get()
            popup.destroy()
            if sel == "Xem camera":
                self._start_preview_in_thread(node_id)
            elif sel == "Bật/Tắt camera":
                self._start_toggle_in_thread(node_id)

        tk.Button(popup, text="OK", command=run_and_close).pack(pady=6)

    def _schedule_gui(self, callback):
        """Chạy callback trên thread GUI (tránh gọi tk từ thread khác)."""
        try:
            self.window.after(0, callback)
        except tk.TclError:
            pass

    def _start_preview_in_thread(self, node_id):
        """Tạo cửa sổ preview, worker push frame vào queue, GUI đọc bằng after()."""
        if not self.camera_manager:
            return
        cam_id = self.camera_manager.get_cam_id_for_node(node_id)
        if cam_id is None:
            return

        top = tk.Toplevel(self.window)
        top.title(f"Camera: {node_id}")
        top.geometry("640x480")
        label = tk.Label(top, text="Waiting for frame...")
        label.pack(fill=tk.BOTH, expand=1)

        photo_ref = []
        frame_queue = queue.Queue(maxsize=1)
        running = {"running": True}

        def on_close():
            running["running"] = False
            # Clear queue + image refs để GC dễ hơn
            try:
                while True:
                    frame_queue.get_nowait()
            except queue.Empty:
                pass
            photo_ref.clear()
            if top in self._preview_windows:
                self._preview_windows.remove(top)
            top.destroy()

        top.protocol("WM_DELETE_WINDOW", on_close)
        self._preview_windows.append(top)

        # Worker: đọc frame từ camera_manager.latest_frames, crop ROI (nếu có), push vào queue
        thread = threading.Thread(
            target=self._preview_worker,
            args=(cam_id, node_id, frame_queue, running),
            daemon=True,
            name="PreviewWorker",
        )
        thread.start()

        # GUI loop: đọc từ queue và cập nhật label ~10 fps
        def gui_loop():
            if not running.get("running"):
                return
            try:
                rgb = frame_queue.get_nowait()
            except queue.Empty:
                pass
            else:
                self._apply_preview_frame(label, rgb, photo_ref)
            # 100 ms ~ 10 fps
            self.window.after(100, gui_loop)

        gui_loop()

    def _preview_worker(self, cam_id, node_id, frame_queue, running, min_interval=0.1):
        """Worker: đọc frame, vẽ ROI lên frame (nếu có), push vào queue với throttle 6–10 fps."""
        roi = self._get_roi_for_node(node_id)  # [x, y, w, h] hoặc None
        last_push = 0.0
        while running.get("running"):
            try:
                frames = getattr(self.camera_manager, "latest_frames", {})
                frame = frames.get(cam_id)
                now = time.time()
                # Throttle: chỉ gửi frame mới nếu đủ interval
                if frame is not None and (now - last_push) >= min_interval:
                    frame = frame.copy()
                    # Vẽ ROI lên frame nếu có
                    if roi is not None and len(roi) >= 4:
                        x, y, w, h = int(roi[0]), int(roi[1]), int(roi[2]), int(roi[3])
                        pt1 = (x, y)
                        pt2 = (x + w, y + h)
                        cv2.rectangle(frame, pt1, pt2, (0, 255, 0), 2)
                        cv2.putText(frame, node_id[:20], (x, max(0, y - 5)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w = rgb.shape[:2]
                    scale = min(640 / w, 480 / h, 1.0)
                    if scale < 1:
                        nw, nh = int(w * scale), int(h * scale)
                        rgb = cv2.resize(rgb, (nw, nh))
                    rgb_copy = rgb.copy()
                    # Queue chuyên cho GUI: drop frame cũ nếu đầy
                    if frame_queue.full():
                        try:
                            frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                    try:
                        frame_queue.put_nowait(rgb_copy)
                        last_push = now
                    except queue.Full:
                        pass
            except Exception:
                pass
            time.sleep(0.01)

    def _apply_preview_frame(self, label, rgb, photo_ref):
        """Chạy trên GUI thread: vẽ frame lên label."""
        try:
            img = Image.fromarray(rgb)
            photo = ImageTk.PhotoImage(image=img)
            photo_ref.append(photo)
            label.config(image=photo, text="")
        except (tk.TclError, Exception):
            pass

    def _start_toggle_in_thread(self, node_id):
        """Toggle camera trên worker thread, cập nhật checkbox trên GUI thread."""
        if not self.camera_manager:
            return
        info = self.camera_manager._node_id_to_cam.get(node_id)
        if info is None:
            return
        cam_id, idx = info  # idx = camera index (int), cam_id = string

        def worker():
            with self.camera_manager._enabled_lock:
                if idx >= len(self.camera_manager.enabled):
                    return
                new_state = not self.camera_manager.enabled[idx]
            self.camera_manager.set_camera_enabled(idx, new_state)
            self._schedule_gui(lambda: self._sync_checkbox(cam_id, new_state))

        threading.Thread(target=worker, daemon=True, name="ToggleWorker").start()

    def _set_camera_button_color(self, cam_id, enabled):
        """Đã bỏ checkbox camera, hàm này giữ cho tương thích, không làm gì."""
        return

    def _sync_checkbox(self, cam_id, new_state):
        """Không còn checkbox camera để đồng bộ; pair Cam được tô màu trong update_display."""
        return

    def toggle_flag(self, point_id, flag_type):
        # Ưu tiên gọi API nếu có camera_api_client
        if self.camera_api_client:
            self.camera_api_client.toggle_node_flag(point_id)
            self.update_display()
            return
        
        # Fallback: local state manager
        if point_id not in self.state_manager.points:
            return
        point_data = self.state_manager.points[point_id]
        current_flag = point_data["flag"]
        point_data["flag"] = not current_flag
        self.update_display()

    def _get_camera_enabled_for_node(self, node_id):
        """Trả về (enabled: bool | None) cho 1 node_id dựa trên CameraManager._node_id_to_cam."""
        if not self.camera_manager:
            return None
        info = getattr(self.camera_manager, "_node_id_to_cam", {}).get(node_id)
        if not info:
            return None
        _, idx = info
        try:
            with self.camera_manager._enabled_lock:
                if 0 <= idx < len(self.camera_manager.enabled):
                    return bool(self.camera_manager.enabled[idx])
        except Exception:
            return None
        return None

    def _set_pair_cam_button_color(self, labels, prefix, node_id):
        """Đổi màu nút Cam của pair theo trạng thái camera: xanh = bật, đỏ = tắt, xám = không map."""
        btn_key = f"{prefix}_cam_btn"
        btn = labels.get(btn_key)
        if not btn or not self.camera_manager:
            return
        enabled = self._get_camera_enabled_for_node(node_id)
        try:
            if enabled is True:
                btn.configure(bg="#d0ffd0", activebackground="#b0ffb0")
            elif enabled is False:
                btn.configure(bg="#ffd0d0", activebackground="#ffb0b0")
            else:
                btn.configure(bg="#e0e0e0", activebackground="#d0d0d0")
        except (tk.TclError, Exception):
            pass

    def update_display(self):
        # Refresh state from API if using proxy
        if self.use_proxy and self.state_manager:
            self.state_manager.refresh()
        
        current_time = time.time()
        for row in self.labels:
            start_point = row["start_point"]
            end_point = row["end_point"]
            labels = row["labels"]
            for pt, prefix in [(start_point, "start"), (end_point, "end")]:
                if pt in self.state_manager.points:
                    data = self.state_manager.points[pt]
                    st = data["state"]
                    fl = data["flag"]
                    t = data["time"]
                    labels[f"{prefix}_state"].config(text="T" if st else "F", bg="#00ff00" if st else "#ff0000")
                    labels[f"{prefix}_flag"].config(text="T" if fl else "F", bg="#ffff00" if fl else "#808080")
                    if t > 0:
                        elapsed = current_time - t
                        labels[f"{prefix}_time"].config(text=f"{elapsed:.1f}s", bg="#e8f5e9" if elapsed < 10 else "#ffebee")
                    else:
                        labels[f"{prefix}_time"].config(text="-", bg="white")
                self._set_pair_cam_button_color(labels, prefix, pt)

        for row in self.empty_start_labels:
            start_point = row["start_point"]
            labels = row["labels"]
            if start_point in self.state_manager.points:
                data = self.state_manager.points[start_point]
                st, fl, t = data["state"], data["flag"], data["time"]
                labels["start_state"].config(text="T" if st else "F", bg="#00ff00" if st else "#ff0000")
                labels["start_flag"].config(text="T" if fl else "F", bg="#ffff00" if fl else "#808080")
                if t > 0:
                    elapsed = current_time - t
                    labels["start_time"].config(text=f"{elapsed:.1f}s", bg="#e8f5e9" if elapsed < 10 else "#ffebee")
                else:
                    labels["start_time"].config(text="-", bg="white")
            else:
                labels["start_state"].config(text="F", bg="#ff0000")
                labels["start_flag"].config(text="F", bg="#808080")
                labels["start_time"].config(text="-", bg="white")
            self._set_pair_cam_button_color(labels, "start", start_point)

        self.window.after(500, self.update_display)

    def on_closing(self):
        for w in self._preview_windows[:]:
            try:
                w.destroy()
            except Exception:
                pass
        self._preview_windows.clear()
        if self.shutdown_callback:
            self.window.destroy()
            self.shutdown_callback()
        else:
            self.window.destroy()

    def run(self):
        self.update_display()
        self.window.mainloop()
        logger.info("GUI mainloop ended")
