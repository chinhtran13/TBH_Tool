import ctypes
import json
import threading
import time
import tkinter as tk
import base64
import sys
import subprocess
import urllib.request
import urllib.error
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk

CURRENT_VERSION = "v1.0.1"
GITHUB_OWNER = "chinhtran13"
GITHUB_REPO = "TBH_Tool"


CONFIG_PATH = Path(__file__).with_name("inventory_bag_monitor_config.json")
CAPTURE_DIR = Path(__file__).with_name("captures")
PROFILES_DIR = Path(__file__).with_name("profiles")

SRCCOPY = 0x00CC0020
BI_RGB = 0
DIB_RGB_COLORS = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

# Win32 constants for click-through overlay
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020


user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


@dataclass
class Rect:
    x: int
    y: int
    width: int
    height: int

    def to_dict(self):
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            x=int(data["x"]),
            y=int(data["y"]),
            width=int(data["width"]),
            height=int(data["height"]),
        )


def get_cursor_pos():
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def set_cursor_pos(x, y):
    user32.SetCursorPos(int(x), int(y))


def left_click(x, y):
    set_cursor_pos(x, y)
    time.sleep(0.03)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.03)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def long_click(x, y):
    """Click and hold at (x, y) for hold_sec seconds."""
    set_cursor_pos(x, y)
    time.sleep(0.03)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.03)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


# SM_XVIRTUALSCREEN=76, SM_YVIRTUALSCREEN=77, SM_CXVIRTUALSCREEN=78, SM_CYVIRTUALSCREEN=79
def get_virtual_screen():
    """Return (x, y, width, height) covering all monitors."""
    vx = user32.GetSystemMetrics(76)
    vy = user32.GetSystemMetrics(77)
    vw = user32.GetSystemMetrics(78)
    vh = user32.GetSystemMetrics(79)
    return vx, vy, vw, vh


def capture_region(rect: Rect):
    if rect.width <= 0 or rect.height <= 0:
        raise ValueError("Region must have positive width and height.")

    screen_dc = user32.GetDC(0)
    memory_dc = gdi32.CreateCompatibleDC(screen_dc)
    bitmap = gdi32.CreateCompatibleBitmap(screen_dc, rect.width, rect.height)
    gdi32.SelectObject(memory_dc, bitmap)
    gdi32.BitBlt(memory_dc, 0, 0, rect.width, rect.height, screen_dc, rect.x, rect.y, SRCCOPY)

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = rect.width
    bmi.bmiHeader.biHeight = -rect.height
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = BI_RGB

    size = rect.width * rect.height * 4
    buffer = ctypes.create_string_buffer(size)
    lines = gdi32.GetDIBits(memory_dc, bitmap, 0, rect.height, buffer, ctypes.byref(bmi), DIB_RGB_COLORS)

    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory_dc)
    user32.ReleaseDC(0, screen_dc)

    if lines != rect.height:
        raise RuntimeError("Failed to capture screen region.")

    return bytes(buffer)


def diff_ratio(a: bytes, b: bytes):
    if len(a) != len(b):
        return 1.0

    if not a:
        return 0.0

    changed_channels = 0
    total_channels = len(a)
    for left, right in zip(a, b):
        if abs(left - right) > 12:
            changed_channels += 1
    return changed_channels / total_channels




class RegionSelector(tk.Toplevel):
    def __init__(self, master, title, callback):
        super().__init__(master)
        self.callback = callback
        self.start_x = 0
        self.start_y = 0
        self.rect_outline_id = None
        self.rect_fill_id = None
        self.size_label_id = None
        self.crosshair_h = None
        self.crosshair_v = None

        self.overrideredirect(True)
        vx, vy, vw, vh = get_virtual_screen()
        self.geometry(f"{vw}x{vh}+{vx}+{vy}")
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.3)
        self.configure(bg="black")
        self.title(title)
        # Store virtual screen offset so canvas coords map to screen coords
        self.vx = vx
        self.vy = vy

        self.canvas = tk.Canvas(self, bg="gray10", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

        self.hint_label = tk.Label(
            self,
            text="Kéo chuột để chọn vùng. Nhấn ESC để hủy.",
            bg="gold",
            fg="black",
            font=("Segoe UI", 12, "bold"),
        )
        self.hint_label.place(x=20, y=20)

        # Draw initial crosshair lines following mouse before drag starts
        self.canvas.bind("<Motion>", self.on_motion_before_drag)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Escape>", lambda _: self.destroy())

    def on_motion_before_drag(self, event):
        # Show crosshair lines following mouse before user starts dragging
        if self.crosshair_h is not None:
            self.canvas.delete(self.crosshair_h)
        if self.crosshair_v is not None:
            self.canvas.delete(self.crosshair_v)
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        self.crosshair_h = self.canvas.create_line(0, event.y, w, event.y, fill="#00FF00", width=1, dash=(4, 4))
        self.crosshair_v = self.canvas.create_line(event.x, 0, event.x, h, fill="#00FF00", width=1, dash=(4, 4))

    def clear_visuals(self):
        for item in [self.rect_fill_id, self.rect_outline_id, self.size_label_id,
                      self.crosshair_h, self.crosshair_v]:
            if item is not None:
                self.canvas.delete(item)
        self.rect_fill_id = None
        self.rect_outline_id = None
        self.size_label_id = None
        self.crosshair_h = None
        self.crosshair_v = None

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.start_x_root = event.x_root
        self.start_y_root = event.y_root
        # Unbind pre-drag motion
        self.canvas.unbind("<Motion>")
        # Clean up all previous visuals
        self.clear_visuals()
        # Semi-transparent fill rectangle (stipple gives a fill pattern effect)
        self.rect_fill_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            fill="#00AAFF", stipple="gray25", outline="",
        )
        # Bright outline rectangle
        self.rect_outline_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="#00FF00", width=2,
        )
        # Size label
        self.size_label_id = self.canvas.create_text(
            self.start_x, self.start_y - 10,
            text="0 x 0", fill="#00FF00", font=("Segoe UI", 11, "bold"), anchor="sw",
        )

    def on_drag(self, event):
        if self.rect_outline_id is not None:
            self.canvas.coords(self.rect_fill_id, self.start_x, self.start_y, event.x, event.y)
            self.canvas.coords(self.rect_outline_id, self.start_x, self.start_y, event.x, event.y)
            w = abs(event.x - self.start_x)
            h = abs(event.y - self.start_y)
            label_x = min(self.start_x, event.x)
            label_y = min(self.start_y, event.y) - 6
            self.canvas.coords(self.size_label_id, label_x, label_y)
            self.canvas.itemconfig(self.size_label_id, text=f"{w} x {h}")

    def on_release(self, event):
        x1, y1 = self.start_x, self.start_y
        x2, y2 = event.x, event.y
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        if width < 3 or height < 3:
            # Too small, allow re-drag
            self.canvas.bind("<Motion>", self.on_motion_before_drag)
            return
        # Use x_root/y_root for accurate screen coordinates
        left = min(self.start_x_root, event.x_root)
        top = min(self.start_y_root, event.y_root)
        self.callback(Rect(left, top, width, height))
        self.destroy()


class PointSelector(tk.Toplevel):
    def __init__(self, master, title, hint_text, callback):
        super().__init__(master)
        self.callback = callback
        self.crosshair_h = None
        self.crosshair_v = None
        self.coord_label_id = None
        self.dot_id = None

        self.overrideredirect(True)
        vx, vy, vw, vh = get_virtual_screen()
        self.geometry(f"{vw}x{vh}+{vx}+{vy}")
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.3)
        self.configure(bg="black")
        self.title(title)
        # Store virtual screen offset
        self.vx = vx
        self.vy = vy

        self.canvas = tk.Canvas(self, bg="gray10", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

        self.hint_label = tk.Label(
            self,
            text=hint_text,
            bg="gold",
            fg="black",
            font=("Segoe UI", 12, "bold"),
        )
        self.hint_label.place(x=20, y=20)

        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<ButtonPress-1>", self.on_click)
        self.bind("<Escape>", lambda _: self.destroy())

    def on_motion(self, event):
        # Clean up previous crosshair elements
        for item in [self.crosshair_h, self.crosshair_v, self.coord_label_id, self.dot_id]:
            if item is not None:
                self.canvas.delete(item)
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        # Full-screen crosshair lines
        self.crosshair_h = self.canvas.create_line(0, event.y, w, event.y, fill="#FF4444", width=1, dash=(6, 3))
        self.crosshair_v = self.canvas.create_line(event.x, 0, event.x, h, fill="#FF4444", width=1, dash=(6, 3))
        # Center dot at cursor position
        r = 4
        self.dot_id = self.canvas.create_oval(
            event.x - r, event.y - r, event.x + r, event.y + r,
            fill="#FF4444", outline="white", width=1,
        )
        # Coordinate label near cursor
        self.coord_label_id = self.canvas.create_text(
            event.x + 14, event.y - 14,
            text=f"({event.x_root}, {event.y_root})",
            fill="#FF4444", font=("Segoe UI", 11, "bold"), anchor="sw",
        )

    def on_click(self, event):
        # Use x_root/y_root for accurate screen coordinates
        self.callback(event.x_root, event.y_root)
        self.destroy()


class OverlayWindow(tk.Toplevel):
    """Persistent semi-transparent overlay showing configured regions and points.
    Click-through so it doesn't block mouse input."""

    def __init__(self, master):
        super().__init__(master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.45)
        self.configure(bg="black")

        # Cover all monitors
        vx, vy, vw, vh = get_virtual_screen()
        self.geometry(f"{vw}x{vh}+{vx}+{vy}")

        self.canvas = tk.Canvas(
            self, bg="black", highlightthickness=0,
            width=vw, height=vh,
        )
        self.canvas.pack(fill="both", expand=True)

        # Make the window click-through after it's shown
        self.after(50, self.make_click_through)

    def make_click_through(self):
        hwnd = int(self.wm_frame(), 16) if self.wm_frame() else self.winfo_id()
        try:
            # Try with wm_frame first (decorated windows)
            hwnd = int(self.wm_frame(), 16)
        except (ValueError, TypeError):
            hwnd = self.winfo_id()
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)

    def draw(self, regions, points):
        """Draw regions (list of (label, Rect, color)) and points (list of (label, x, y, color))."""
        self.canvas.delete("all")
        # Offset to convert screen coords to canvas coords
        vx, vy, _, _ = get_virtual_screen()
        for label, rect, color in regions:
            rx = rect.x - vx
            ry = rect.y - vy
            # Draw filled rectangle with stipple
            self.canvas.create_rectangle(
                rx, ry, rx + rect.width, ry + rect.height,
                outline=color, width=2, fill=color, stipple="gray12",
            )
            # Draw label
            self.canvas.create_text(
                rx + 4, ry + 4,
                text=f"{label} ({rect.width}x{rect.height})",
                fill=color, font=("Segoe UI", 10, "bold"), anchor="nw",
            )
        for label, x, y, color in points:
            px = x - vx
            py = y - vy
            # Draw crosshair at point
            arm = 14
            self.canvas.create_line(px - arm, py, px + arm, py, fill=color, width=2)
            self.canvas.create_line(px, py - arm, px, py + arm, fill=color, width=2)
            # Draw dot
            r = 4
            self.canvas.create_oval(px - r, py - r, px + r, py + r, fill=color, outline="white", width=1)
            # Draw label
            self.canvas.create_text(
                px + 12, py - 12,
                text=f"{label} ({x},{y})",
                fill=color, font=("Segoe UI", 9, "bold"), anchor="sw",
            )


def send_telegram(bot_token, chat_id, message):
    """Send a message via Telegram Bot API. Returns True on success."""
    if not bot_token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Theo dõi túi đồ")
        self.root.geometry("860x680")
        self.root.resizable(True, True)
        self.root.minsize(700, 400)

        self.running = False
        self.worker = None
        self.condition_baseline = None
        self.bag_full_baseline = None
        self.condition_triggered = False
        self.bag_triggered = False
        self.current_bag_index = 0
        self.switch_points = []
        self.overlay_window = None
        self.cleanup_points = []

        self.vars = {
            "condition_x": tk.StringVar(),
            "condition_y": tk.StringVar(),
            "condition_w": tk.StringVar(),
            "condition_h": tk.StringVar(),
            "bag_x": tk.StringVar(),
            "bag_y": tk.StringVar(),
            "bag_w": tk.StringVar(),
            "bag_h": tk.StringVar(),
            "action_x": tk.StringVar(),
            "action_y": tk.StringVar(),
            "sort_x": tk.StringVar(),
            "sort_y": tk.StringVar(),
            "poll_ms": tk.StringVar(value="700"),
            "condition_threshold": tk.StringVar(value="0.035"),
            "bag_threshold": tk.StringVar(value="0.035"),
            "action_delay_ms": tk.StringVar(value="1200"),
            "switch_delay_ms": tk.StringVar(value="1600"),
            "cleanup_repeat": tk.StringVar(value="5"),
            "cleanup_delay_ms": tk.StringVar(value="2000"),
        }

        self.log_text = None
        self.status_var = tk.StringVar(value="Đang chờ cấu hình.")

        self.build_ui()
        self.load_config()
        self.log("Sẵn sàng. Chọn 2 vùng, điểm click hành động và danh sách vị trí túi.")
        
        # Chạy luồng ngầm kiểm tra cập nhật tự động
        threading.Thread(target=self.check_for_updates, daemon=True).start()


    def build_ui(self):
        # Scrollable container
        scroll_container = ttk.Frame(self.root)
        scroll_container.pack(fill="both", expand=True)

        canvas = tk.Canvas(scroll_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        outer = ttk.Frame(canvas, padding=12)
        canvas_window = canvas.create_window((0, 0), window=outer, anchor="nw")

        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        outer.bind("<Configure>", on_frame_configure)
        canvas.bind("<Configure>", on_canvas_configure)

        # Mouse wheel scrolling
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def bind_mousewheel(event):
            canvas.bind_all("<MouseWheel>", on_mousewheel)

        def unbind_mousewheel(event):
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", bind_mousewheel)
        canvas.bind("<Leave>", unbind_mousewheel)

        section1 = ttk.LabelFrame(outer, text="Vùng 1 - Điều kiện thay đổi")
        section1.pack(fill="x", pady=4)
        self.build_region_block(section1, "condition", "Chọn vùng 1")

        section2 = ttk.LabelFrame(outer, text="Vùng 2 - Kiểm tra đầy túi")
        section2.pack(fill="x", pady=4)
        self.build_region_block(section2, "bag", "Chọn vùng 2")

        click_section = ttk.LabelFrame(outer, text="Điểm click")
        click_section.pack(fill="x", pady=4)
        self.build_point_row(click_section, "Vị trí click hành động", "action", 0)
        self.build_point_row(click_section, "Vị trí sắp xếp (để trống nếu không dùng)", "sort", 1)

        bag_list_section = ttk.LabelFrame(outer, text="Danh sách vị trí các túi tiếp theo")
        bag_list_section.pack(fill="x", pady=4)
        ttk.Label(
            bag_list_section,
            text="Mỗi dòng là một túi theo định dạng: x,y. Dòng 1 là túi 2, dòng 2 là túi 3, ...",
        ).pack(anchor="w", padx=6, pady=(6, 2))
        self.bag_positions_text = tk.Text(bag_list_section, height=8, width=60)
        self.bag_positions_text.pack(fill="x", padx=6, pady=4)
        bag_list_actions = ttk.Frame(bag_list_section)
        bag_list_actions.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(
            bag_list_actions,
            text="Thêm vị trí túi bằng 1 lần click",
            command=self.capture_next_bag_position,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            bag_list_actions,
            text="Xóa danh sách túi",
            command=self.clear_bag_positions,
        ).pack(side="left")

        settings = ttk.LabelFrame(outer, text="Thông số")
        settings.pack(fill="x", pady=4)
        rows = [
            ("Chu kỳ quét (ms)", "poll_ms"),
            ("Ngưỡng thay đổi vùng 1", "condition_threshold"),
            ("Ngưỡng thay đổi vùng 2", "bag_threshold"),
            ("Trễ sau click hành động (ms)", "action_delay_ms"),
            ("Trễ sau đổi túi (ms)", "switch_delay_ms"),
            ("Số lần dọn kho", "cleanup_repeat"),
            ("Trễ giữa mỗi lần dọn (ms)", "cleanup_delay_ms"),
        ]
        for index, (label, key) in enumerate(rows):
            ttk.Label(settings, text=label, width=26).grid(row=index, column=0, padx=6, pady=3, sticky="w")
            ttk.Entry(settings, textvariable=self.vars[key], width=18).grid(row=index, column=1, padx=6, pady=3, sticky="w")

        baseline_section = ttk.LabelFrame(outer, text="Mốc gốc")
        baseline_section.pack(fill="x", pady=4)
        ttk.Button(baseline_section, text="Chụp mốc gốc vùng 1 + vùng 2", command=self.capture_baselines).pack(side="left", padx=6, pady=8)
        ttk.Button(baseline_section, text="Hiện/Ẩn vùng đã chọn", command=self.toggle_overlay).pack(side="left", padx=6, pady=8)


        profile_section = ttk.LabelFrame(outer, text="Cấu hình")
        profile_section.pack(fill="x", pady=4)
        ttk.Label(profile_section, text="Tên cấu hình").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        self.profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(profile_section, textvariable=self.profile_var, width=25, state="readonly")
        self.profile_combo.grid(row=0, column=1, padx=6, pady=6, sticky="w")
        self.profile_combo.bind("<<ComboboxSelected>>", lambda _: self.load_profile())
        ttk.Button(profile_section, text="Lưu cấu hình", command=self.save_config).grid(row=0, column=2, padx=4, pady=6)
        ttk.Button(profile_section, text="Lưu thành mới...", command=self.save_profile_as).grid(row=0, column=3, padx=4, pady=6)
        ttk.Button(profile_section, text="Xóa", command=self.delete_profile).grid(row=0, column=4, padx=4, pady=6)
        self.refresh_profiles()

        cleanup_section = ttk.LabelFrame(outer, text="Vị trí dọn kho (click lần lượt khi tất cả túi đầy)")
        cleanup_section.pack(fill="x", pady=4)
        ttk.Label(
            cleanup_section,
            text="Mỗi dòng là một vị trí click theo định dạng: x,y. Click lần lượt 1→2→3 mỗi lần.",
        ).pack(anchor="w", padx=6, pady=(6, 2))
        self.cleanup_positions_text = tk.Text(cleanup_section, height=4, width=60)
        self.cleanup_positions_text.pack(fill="x", padx=6, pady=4)
        cleanup_actions = ttk.Frame(cleanup_section)
        cleanup_actions.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(
            cleanup_actions,
            text="Thêm vị trí bằng 1 lần click",
            command=self.capture_cleanup_position,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            cleanup_actions,
            text="Xóa danh sách",
            command=self.clear_cleanup_positions,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            cleanup_actions,
            text="Test dọn kho (1 lần)",
            command=self.test_cleanup,
        ).pack(side="left")

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=8)
        ttk.Button(actions, text="Bật giám sát", command=self.start_monitoring).pack(side="left", padx=6)
        ttk.Button(actions, text="Dừng", command=self.stop_monitoring).pack(side="left", padx=6)
        ttk.Button(actions, text="Test toàn bộ (1 lượt)", command=self.test_all).pack(side="left", padx=6)

        status = ttk.Label(outer, textvariable=self.status_var, relief="sunken", anchor="w")
        status.pack(fill="x", pady=(0, 6))

        log_box = ttk.LabelFrame(outer, text="Nhật ký")
        log_box.pack(fill="both", expand=True)
        self.log_text = tk.Text(
            log_box,
            height=16,
            width=90,
            state="disabled",
            wrap="word",
            bg="white",
            fg="black",
            insertbackground="black",
            relief="solid",
            borderwidth=1,
        )
        self.log_text.pack(fill="both", expand=True, padx=6, pady=6)

    def build_region_block(self, parent, prefix, button_text):
        fields = [("X", "x"), ("Y", "y"), ("W", "w"), ("H", "h")]
        for column, (label, suffix) in enumerate(fields):
            ttk.Label(parent, text=label).grid(row=0, column=column * 2, padx=4, pady=6, sticky="w")
            ttk.Entry(parent, textvariable=self.vars[f"{prefix}_{suffix}"], width=10).grid(
                row=0, column=column * 2 + 1, padx=4, pady=6, sticky="w"
            )
        ttk.Button(parent, text=button_text, command=lambda: self.select_region(prefix)).grid(
            row=0, column=8, padx=8, pady=6, sticky="w"
        )

    def build_point_row(self, parent, label, prefix, row):
        ttk.Label(parent, text=label, width=24).grid(row=row, column=0, padx=6, pady=6, sticky="w")
        ttk.Label(parent, text="X").grid(row=row, column=1, padx=4, pady=6, sticky="w")
        ttk.Entry(parent, textvariable=self.vars[f"{prefix}_x"], width=10).grid(row=row, column=2, padx=4, pady=6, sticky="w")
        ttk.Label(parent, text="Y").grid(row=row, column=3, padx=4, pady=6, sticky="w")
        ttk.Entry(parent, textvariable=self.vars[f"{prefix}_y"], width=10).grid(row=row, column=4, padx=4, pady=6, sticky="w")
        ttk.Button(parent, text="Chọn vị trí bằng 1 lần click", command=lambda: self.capture_point(prefix)).grid(
            row=row, column=5, padx=8, pady=6, sticky="w"
        )

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.status_var.set(message)

    def select_region(self, prefix):
        label = "vùng 1" if prefix == "condition" else "vùng 2"
        self.log(f"Đang chờ bạn kéo để chọn {label}.")
        self.root.after(150, lambda: RegionSelector(self.root, prefix, lambda rect: self.set_region(prefix, rect)))

    def set_region(self, prefix, rect: Rect):
        self.vars[f"{prefix}_x"].set(str(rect.x))
        self.vars[f"{prefix}_y"].set(str(rect.y))
        self.vars[f"{prefix}_w"].set(str(rect.width))
        self.vars[f"{prefix}_h"].set(str(rect.height))
        label = "vùng 1" if prefix == "condition" else "vùng 2"
        self.log(f"Đã chọn {label}: x={rect.x}, y={rect.y}, w={rect.width}, h={rect.height}.")

    def capture_point(self, prefix):
        self.log("Hãy click một cái vào vị trí hành động để xác định tọa độ.")
        self.status_var.set("Đang chờ bạn click để lấy vị trí hành động...")
        self.root.after(
            150,
            lambda: PointSelector(
                self.root,
                "Chọn vị trí hành động",
                "Click 1 cái để chọn vị trí hành động. Nhấn ESC để hủy.",
                lambda x, y: self.finish_capture_point(prefix, x, y),
            ),
        )

    def finish_capture_point(self, prefix, x, y):
        self.vars[f"{prefix}_x"].set(str(x))
        self.vars[f"{prefix}_y"].set(str(y))
        self.log(f"Đã lấy vị trí hành động: x={x}, y={y}.")

    def capture_next_bag_position(self):
        self.log("Hãy click một cái vào vị trí túi tiếp theo để xác định tọa độ.")
        self.status_var.set("Đang chờ bạn click để lấy vị trí túi tiếp theo...")
        self.root.after(
            150,
            lambda: PointSelector(
                self.root,
                "Chọn vị trí túi",
                "Click 1 cái để thêm vị trí túi tiếp theo. Nhấn ESC để hủy.",
                self.finish_capture_next_bag_position,
            ),
        )

    def finish_capture_next_bag_position(self, x, y):
        current = self.bag_positions_text.get("1.0", "end").strip()
        next_line = f"{x},{y}"
        updated = f"{current}\n{next_line}".strip() if current else next_line
        self.bag_positions_text.delete("1.0", "end")
        self.bag_positions_text.insert("1.0", updated)
        bag_number = len(self.parse_switch_points())
        self.log(f"Đã thêm vị trí túi {bag_number + 1}: x={x}, y={y}.")

    def clear_bag_positions(self):
        self.bag_positions_text.delete("1.0", "end")
        self.log("Đã xóa danh sách vị trí các túi tiếp theo.")

    def toggle_overlay(self):
        # If overlay is currently visible, close it
        if self.overlay_window is not None:
            try:
                self.overlay_window.destroy()
            except Exception:
                pass
            self.overlay_window = None
            self.log("Đã ẩn overlay vùng đã chọn.")
            return

        # Collect regions
        regions = []
        try:
            condition_rect = self.get_rect("condition")
            regions.append(("Vùng 1", condition_rect, "#00FF00"))
        except ValueError:
            pass
        try:
            bag_rect = self.get_rect("bag")
            regions.append(("Vùng 2", bag_rect, "#00AAFF"))
        except ValueError:
            pass

        # Collect points
        points = []
        action_pt = self.get_point("action", optional=True)
        if action_pt is not None:
            points.append(("Click hành động", action_pt[0], action_pt[1], "#FF4444"))
        try:
            switch_pts = self.parse_switch_points()
            for idx, (sx, sy) in enumerate(switch_pts):
                points.append((f"Túi {idx + 2}", sx, sy, "#FFaa00"))
        except ValueError:
            pass
        try:
            cleanup_pts = self.parse_cleanup_points()
            for idx, (cx, cy) in enumerate(cleanup_pts):
                points.append((f"Dọn kho {idx + 1}", cx, cy, "#FF00FF"))
        except ValueError:
            pass

        if not regions and not points:
            messagebox.showinfo("Thông báo", "Chưa có vùng hoặc điểm nào được cấu hình.")
            return

        self.overlay_window = OverlayWindow(self.root)
        self.overlay_window.draw(regions, points)
        self.log("Đã hiện overlay vùng đã chọn. Bấm lại nút để ẩn.")

    def get_rect(self, prefix):
        try:
            return Rect(
                x=int(self.vars[f"{prefix}_x"].get()),
                y=int(self.vars[f"{prefix}_y"].get()),
                width=int(self.vars[f"{prefix}_w"].get()),
                height=int(self.vars[f"{prefix}_h"].get()),
            )
        except ValueError:
            label = "vùng 1" if prefix == "condition" else "vùng 2"
            raise ValueError(f"Tọa độ {label} chưa hợp lệ.")

    def get_point(self, prefix, optional=False):
        x_raw = self.vars[f"{prefix}_x"].get().strip()
        y_raw = self.vars[f"{prefix}_y"].get().strip()
        if optional and (not x_raw or not y_raw):
            return None
        try:
            return int(x_raw), int(y_raw)
        except ValueError:
            if optional:
                return None
            raise ValueError("Điểm click hành động chưa hợp lệ.")

    def capture_baselines(self):
        try:
            condition_rect = self.get_rect("condition")
            bag_rect = self.get_rect("bag")
            self.condition_baseline = capture_region(condition_rect)
            self.bag_full_baseline = capture_region(bag_rect)
            self.original_condition_baseline = self.condition_baseline
            self.original_bag_baseline = self.bag_full_baseline
            self.condition_triggered = False
            self.bag_triggered = False
            self.log("Đã chụp mốc gốc cho cả 2 vùng.")
        except Exception as exc:
            messagebox.showerror("Lỗi", str(exc))

    def capture_current_regions(self):
        condition_rect = self.get_rect("condition")
        bag_rect = self.get_rect("bag")
        condition_image = capture_region(condition_rect)
        bag_image = capture_region(bag_rect)
        return (
            ("Vùng 1", condition_rect, condition_image),
            ("Vùng 2", bag_rect, bag_image),
        )


    def parse_switch_points(self):
        points = []
        raw_lines = self.bag_positions_text.get("1.0", "end").splitlines()
        for index, line in enumerate(raw_lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                x_text, y_text = [part.strip() for part in stripped.split(",", 1)]
                points.append((int(x_text), int(y_text)))
            except ValueError as exc:
                raise ValueError(f"Dòng vị trí túi số {index} chưa đúng định dạng x,y.") from exc
        return points

    def validate_ready(self):
        self.get_rect("condition")
        self.get_rect("bag")
        self.get_point("action")
        switches = self.parse_switch_points()
        if not switches:
            raise ValueError("Cần ít nhất một vị trí túi tiếp theo.")
        for key in ["poll_ms", "action_delay_ms", "switch_delay_ms"]:
            int(self.vars[key].get())
        for key in ["condition_threshold", "bag_threshold"]:
            float(self.vars[key].get())

    def start_monitoring(self):
        if self.running:
            return
        try:
            self.validate_ready()
            if self.condition_baseline is None or self.bag_full_baseline is None:
                self.capture_baselines()
            self.switch_points = self.parse_switch_points()
        except Exception as exc:
            messagebox.showerror("Lỗi cấu hình", str(exc))
            return

        self.running = True
        self.current_bag_index = 0
        self.cleanup_points = self.parse_cleanup_points()
        self.worker = threading.Thread(target=self.monitor_loop, daemon=True)
        self.worker.start()
        self.log("Đã bật giám sát. Đang theo dõi vùng 1 và vùng 2.")

    def stop_monitoring(self):
        self.running = False
        self.log("Đã dừng giám sát.")

    def safe_log(self, message):
        self.root.after(0, lambda: self.log(message))

    def recapture_bag_baseline(self):
        self.bag_full_baseline = capture_region(self.get_rect("bag"))
        # Reset trigger states so vùng 1 sẽ được quét/click lại nếu đồ vẫn còn sau khi đổi túi.
        self.condition_triggered = False
        self.bag_triggered = False

    def parse_cleanup_points(self):
        points = []
        raw_lines = self.cleanup_positions_text.get("1.0", "end").splitlines()
        for index, line in enumerate(raw_lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                x_text, y_text = [part.strip() for part in stripped.split(",", 1)]
                points.append((int(x_text), int(y_text)))
            except ValueError as exc:
                raise ValueError(f"Dòng vị trí dọn kho số {index} chưa đúng định dạng x,y.") from exc
        return points

    def capture_cleanup_position(self):
        self.log("Hãy click vào vị trí dọn kho tiếp theo.")
        self.status_var.set("Đang chờ bạn click để lấy vị trí dọn kho...")
        self.root.after(
            150,
            lambda: PointSelector(
                self.root,
                "Chọn vị trí dọn kho",
                "Click 1 cái để thêm vị trí dọn kho. Nhấn ESC để hủy.",
                self.finish_capture_cleanup_position,
            ),
        )

    def finish_capture_cleanup_position(self, x, y):
        current = self.cleanup_positions_text.get("1.0", "end").strip()
        next_line = f"{x},{y}"
        updated = f"{current}\n{next_line}".strip() if current else next_line
        self.cleanup_positions_text.delete("1.0", "end")
        self.cleanup_positions_text.insert("1.0", updated)
        count = len(self.parse_cleanup_points())
        self.log(f"Đã thêm vị trí dọn kho {count}: x={x}, y={y}.")

    def clear_cleanup_positions(self):
        self.cleanup_positions_text.delete("1.0", "end")
        self.log("Đã xóa danh sách vị trí dọn kho.")

    def test_cleanup(self):
        """Run cleanup sequence once to test positions."""
        try:
            points = self.parse_cleanup_points()
        except ValueError as exc:
            messagebox.showerror("Lỗi", str(exc))
            return
        if not points:
            messagebox.showwarning("Thiếu thông tin", "Chưa có vị trí dọn kho nào.")
            return
        self.log(f"Test dọn kho: {len(points)} vị trí, 1 lần...")
        def run_test():
            for idx, (cx, cy) in enumerate(points, start=1):
                left_click(cx, cy)
                self.safe_log(f"Test click vị trí {idx}/{len(points)} ({cx},{cy})")
                time.sleep(1)
            self.safe_log("Test dọn kho hoàn tất.")
        threading.Thread(target=run_test, daemon=True).start()

    def test_all(self):
        """Test all positions in order: action → bags → cleanup."""
        try:
            action_pt = self.get_point("action")
            bag_pts = self.parse_switch_points()
            cleanup_pts = self.parse_cleanup_points()
        except ValueError as exc:
            messagebox.showerror("Lỗi", str(exc))
            return
        steps = []
        steps.append(("Click hành động", action_pt[0], action_pt[1]))
        for idx, (bx, by) in enumerate(bag_pts):
            steps.append((f"Đổi túi {idx + 2}", bx, by))
        for idx, (cx, cy) in enumerate(cleanup_pts):
            steps.append((f"Dọn kho {idx + 1}", cx, cy))
        if not steps:
            messagebox.showwarning("Thiếu thông tin", "Chưa có vị trí nào để test.")
            return
        self.log(f"Test toàn bộ: {len(steps)} vị trí...")
        def run_test():
            for idx, (label, x, y) in enumerate(steps, start=1):
                left_click(x, y)
                self.safe_log(f"[{idx}/{len(steps)}] {label} ({x},{y})")
                time.sleep(1)
            self.safe_log("Test toàn bộ hoàn tất.")
        threading.Thread(target=run_test, daemon=True).start()

    def run_cleanup_sequence(self, repeat_count, delay_sec):
        """Click lần lượt qua các vị trí dọn kho, lặp lại repeat_count lần."""
        self.safe_log(f"Bắt đầu dọn kho: {len(self.cleanup_points)} vị trí x {repeat_count} lần.")
        for round_num in range(1, repeat_count + 1):
            if not self.running:
                break
            for idx, (cx, cy) in enumerate(self.cleanup_points, start=1):
                if not self.running:
                    break
                left_click(cx, cy)
                self.safe_log(f"Dọn kho lần {round_num}/{repeat_count} - click vị trí {idx} ({cx},{cy})")
                time.sleep(1)
            if round_num < repeat_count:
                time.sleep(delay_sec)
        self.safe_log(f"Hoàn thành dọn kho {repeat_count} lần.")

    def monitor_loop(self):
        poll_ms = int(self.vars["poll_ms"].get())
        action_delay = int(self.vars["action_delay_ms"].get()) / 1000
        switch_delay = int(self.vars["switch_delay_ms"].get()) / 1000
        condition_threshold = float(self.vars["condition_threshold"].get())
        bag_threshold = float(self.vars["bag_threshold"].get())
        action_point = self.get_point("action")
        cleanup_repeat = int(self.vars["cleanup_repeat"].get())
        cleanup_delay = int(self.vars["cleanup_delay_ms"].get()) / 1000

        while self.running:
            try:
                condition_image = capture_region(self.get_rect("condition"))
                bag_image = capture_region(self.get_rect("bag"))

                condition_ratio = diff_ratio(self.condition_baseline, condition_image)
                bag_ratio = diff_ratio(self.bag_full_baseline, bag_image)

                if condition_ratio >= condition_threshold:
                    if not self.condition_triggered:
                        self.safe_log(f"Vùng 1 thay đổi ({condition_ratio:.3f}). Click hành động.")
                        left_click(*action_point)
                        self.condition_triggered = True
                        time.sleep(action_delay)
                        bag_image = capture_region(self.get_rect("bag"))
                        bag_ratio = diff_ratio(self.bag_full_baseline, bag_image)
                else:
                    self.condition_triggered = False

                if bag_ratio >= bag_threshold:
                    if self.current_bag_index >= len(self.switch_points):
                        # All bags used up — verify region 1 then cleanup
                        self.safe_log("Hết túi trống. Kiểm tra lại vùng 1 để xác nhận...")
                        time.sleep(poll_ms / 1000)
                        recheck_image = capture_region(self.get_rect("condition"))
                        recheck_ratio = diff_ratio(self.condition_baseline, recheck_image)
                        if recheck_ratio >= condition_threshold:
                            self.safe_log(
                                f"Vùng 1 vẫn thay đổi ({recheck_ratio:.3f}). Xác nhận tất cả túi đã đầy!"
                            )
                            if self.cleanup_points:
                                self.run_cleanup_sequence(cleanup_repeat, cleanup_delay)
                                # Reset and restart monitoring with ORIGINAL baselines
                                self.current_bag_index = 0
                                self.condition_triggered = False
                                self.bag_triggered = False
                                self.condition_baseline = self.original_condition_baseline
                                self.bag_full_baseline = self.original_bag_baseline
                                self.safe_log("Dọn kho xong. Đã reset về mốc gốc ban đầu và tiếp tục giám sát.")
                                continue
                            else:
                                self.safe_log("Chưa cấu hình vị trí dọn kho. Dừng giám sát.")
                                self.running = False
                                break
                        else:
                            self.safe_log(
                                f"Vùng 1 đã trở lại bình thường ({recheck_ratio:.3f}). Tiếp tục giám sát."
                            )
                            continue
                    elif not self.bag_triggered:
                        # Switch to next bag, then verify it's not already full
                        while self.current_bag_index < len(self.switch_points):
                            point = self.switch_points[self.current_bag_index]
                            target_bag_number = self.current_bag_index + 2
                            self.safe_log(f"Vùng 2 đầy ({bag_ratio:.3f}). Chuyển sang túi {target_bag_number}.")
                            left_click(*point)
                            self.current_bag_index += 1
                            time.sleep(switch_delay)
                            # Click sort position to reorganize if configured
                            sort_pt = self.get_point("sort", optional=True)
                            if sort_pt:
                                long_click(*sort_pt)
                                self.safe_log(f"Nhấn giữ sắp xếp tại ({sort_pt[0]},{sort_pt[1]}) 1s.")
                                time.sleep(0.5)
                            # Compare new bag against ORIGINAL baseline (not recaptured)
                            verify_bag = capture_region(self.get_rect("bag"))
                            verify_bag_ratio = diff_ratio(self.original_bag_baseline, verify_bag)
                            if verify_bag_ratio >= bag_threshold:
                                # New bag looks different from original empty state → already full
                                self.safe_log(
                                    f"Túi {target_bag_number} đã đầy sẵn (ratio={verify_bag_ratio:.3f} so với mốc gốc). Bỏ qua."
                                )
                                continue  # try next bag in while loop
                            else:
                                # New bag looks similar to original → empty, good!
                                self.safe_log(
                                    f"Túi {target_bag_number} còn trống (ratio={verify_bag_ratio:.3f}). Tiếp tục giám sát."
                                )
                                # Restore original baseline for monitoring this bag
                                self.bag_full_baseline = self.original_bag_baseline
                                break
                        self.bag_triggered = True
                        self.condition_triggered = False
                        continue
                else:
                    self.bag_triggered = False

                time.sleep(poll_ms / 1000)
            except Exception as exc:
                self.safe_log(f"Lỗi khi giám sát: {exc}")
                self.running = False
                break

        self.root.after(0, lambda: self.status_var.set("Đã dừng."))

    def get_config_data(self):
        """Collect current config into a dict."""
        data = {}
        for key, var in self.vars.items():
            data[key] = var.get()
        data["bag_positions"] = self.bag_positions_text.get("1.0", "end").strip()
        data["cleanup_positions"] = self.cleanup_positions_text.get("1.0", "end").strip()
        return data

    def apply_config_data(self, data):
        """Apply a config dict to the UI."""
        for key, value in data.items():
            if key in self.vars:
                self.vars[key].set(str(value))
        bag_positions = data.get("bag_positions", "")
        self.bag_positions_text.delete("1.0", "end")
        self.bag_positions_text.insert("1.0", bag_positions)
        cleanup_positions = data.get("cleanup_positions", "")
        self.cleanup_positions_text.delete("1.0", "end")
        self.cleanup_positions_text.insert("1.0", cleanup_positions)

    def refresh_profiles(self):
        """Refresh the profile dropdown list."""
        PROFILES_DIR.mkdir(exist_ok=True)
        names = sorted(
            p.stem for p in PROFILES_DIR.glob("*.json")
        )
        self.profile_combo["values"] = names

    def save_config(self):
        """Save to the currently selected profile (or default)."""
        name = self.profile_var.get().strip()
        if not name:
            # Fallback: save to legacy config
            data = self.get_config_data()
            CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
            self.log(f"Đã lưu cấu hình vào {CONFIG_PATH.name}.")
            return
        PROFILES_DIR.mkdir(exist_ok=True)
        path = PROFILES_DIR / f"{name}.json"
        data = self.get_config_data()
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.log(f"Đã lưu cấu hình '{name}'.")

    def save_profile_as(self):
        """Save current config with a new name."""
        from tkinter import simpledialog
        name = simpledialog.askstring("Lưu cấu hình mới", "Nhập tên cấu hình:", parent=self.root)
        if not name or not name.strip():
            return
        name = name.strip()
        # Sanitize filename
        safe_name = "".join(c for c in name if c.isalnum() or c in " _-").strip()
        if not safe_name:
            messagebox.showwarning("Lỗi", "Tên cấu hình không hợp lệ.")
            return
        PROFILES_DIR.mkdir(exist_ok=True)
        path = PROFILES_DIR / f"{safe_name}.json"
        data = self.get_config_data()
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.refresh_profiles()
        self.profile_var.set(safe_name)
        self.log(f"Đã lưu cấu hình mới '{safe_name}'.")

    def load_profile(self):
        """Load the selected profile."""
        name = self.profile_var.get().strip()
        if not name:
            return
        path = PROFILES_DIR / f"{name}.json"
        if not path.exists():
            messagebox.showwarning("Lỗi", f"Không tìm thấy cấu hình '{name}'.")
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.apply_config_data(data)
            self.log(f"Đã nạp cấu hình '{name}'.")
        except Exception:
            self.log(f"Không thể nạp cấu hình '{name}'.")

    def delete_profile(self):
        """Delete the selected profile."""
        name = self.profile_var.get().strip()
        if not name:
            messagebox.showwarning("Thông báo", "Chưa chọn cấu hình nào để xóa.")
            return
        path = PROFILES_DIR / f"{name}.json"
        if not path.exists():
            return
        if not messagebox.askyesno("Xác nhận", f"Xóa cấu hình '{name}'?"):
            return
        path.unlink()
        self.profile_var.set("")
        self.refresh_profiles()
        self.log(f"Đã xóa cấu hình '{name}'.")

    def load_config(self):
        """Load legacy config on startup."""
        if not CONFIG_PATH.exists():
            return
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            self.apply_config_data(data)
            self.log(f"Đã nạp cấu hình từ {CONFIG_PATH.name}.")
        except Exception:
            self.log("Không thể nạp cấu hình cũ.")

    def check_for_updates(self):
        """Kiểm tra bản cập nhật mới từ GitHub Releases qua API JSON."""
        time.sleep(1.0)
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "TBH_Tool-Updater"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
            
            tag_name = data.get("tag_name", "").strip()
            if not tag_name:
                return
            
            # So sánh phiên bản hiện tại với tag_name mới nhất
            if tag_name.lower() != CURRENT_VERSION.lower():
                # Tìm file update exe trong danh sách assets
                assets = data.get("assets", [])
                download_url = None
                for asset in assets:
                    name = asset.get("name", "")
                    if name.endswith(".exe"):
                        download_url = asset.get("browser_download_url")
                        break
                
                # Nếu không tìm thấy file .exe, lấy asset đầu tiên (nếu có)
                if not download_url and assets:
                    download_url = assets[0].get("browser_download_url")
                
                if download_url:
                    # Gửi tín hiệu về luồng chính để hiển thị hộp thoại Tkinter
                    self.root.after(0, self.prompt_update, tag_name, download_url)
        except Exception as e:
            print(f"[Updater] Lỗi kiểm tra cập nhật: {e}")

    def prompt_update(self, new_version, download_url):
        """Hiển thị hộp thoại Tkinter hỏi người dùng có muốn cập nhật không."""
        msg = f"Đã tìm thấy phiên bản mới: {new_version}\nPhiên bản hiện tại: {CURRENT_VERSION}\n\nBạn có muốn tải về và tự động cập nhật ngay bây giờ không?"
        if messagebox.askyesno("Phát hiện phiên bản mới", msg, parent=self.root):
            self.download_update(download_url, new_version)

    def download_update(self, download_url, new_version):
        """Hiển thị giao diện tiến trình tải xuống và tiến hành tải file cập nhật."""
        # Tạo cửa sổ hiển thị tiến trình tải
        progress_win = tk.Toplevel(self.root)
        progress_win.title("Đang tải cập nhật...")
        progress_win.geometry("400x130")
        progress_win.resizable(False, False)
        progress_win.transient(self.root)
        progress_win.grab_set()
        
        # Căn giữa cửa sổ con so với cửa sổ chính
        progress_win.update_idletasks()
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        w = progress_win.winfo_width()
        h = progress_win.winfo_height()
        x = rx + (rw - w) // 2
        y = ry + (rh - h) // 2
        progress_win.geometry(f"+{x}+{y}")

        label = ttk.Label(progress_win, text=f"Đang tải bản cập nhật {new_version}...", font=("Segoe UI", 10))
        label.pack(pady=12, padx=20, anchor="w")

        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(progress_win, variable=progress_var, maximum=100)
        progress_bar.pack(fill="x", padx=20, pady=5)

        status_label = ttk.Label(progress_win, text="Đang kết nối...", font=("Segoe UI", 9))
        status_label.pack(pady=5, padx=20, anchor="w")

        self.status_var.set("Đang tải bản cập nhật mới...")
        self.log(f"Bắt đầu tải phiên bản mới {new_version}...")

        def run_download():
            temp_file = Path(sys.argv[0]).parent / "update_new.exe"
            try:
                req = urllib.request.Request(
                    download_url,
                    headers={"User-Agent": "TBH_Tool-Updater"}
                )
                with urllib.request.urlopen(req, timeout=30) as response:
                    total_size = int(response.info().get('Content-Length', 0))
                    downloaded = 0
                    
                    with open(temp_file, "wb") as f:
                        while True:
                            chunk = response.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                progress_var.set(percent)
                                downloaded_mb = downloaded / (1024 * 1024)
                                total_mb = total_size / (1024 * 1024)
                                status_label.config(text=f"Đã tải {downloaded_mb:.2f} MB / {total_mb:.2f} MB ({percent:.1f}%)")
                            else:
                                downloaded_mb = downloaded / (1024 * 1024)
                                status_label.config(text=f"Đã tải {downloaded_mb:.2f} MB")
                            progress_win.update_idletasks()
                
                progress_win.destroy()
                self.root.after(0, self.apply_update_and_restart, temp_file)
            except Exception as e:
                progress_win.destroy()
                self.status_var.set("Tải bản cập nhật thất bại.")
                self.log(f"Lỗi tải cập nhật: {e}")
                messagebox.showerror("Lỗi cập nhật", f"Không thể tải bản cập nhật:\n{e}", parent=self.root)
                if temp_file.exists():
                    try:
                        temp_file.unlink()
                    except Exception:
                        pass

        threading.Thread(target=run_download, daemon=True).start()

    def apply_update_and_restart(self, temp_file):
        """Ghi đè file cũ và tái khởi động ứng dụng (Hot-swap)."""
        is_frozen = getattr(sys, 'frozen', False)
        current_exe = Path(sys.executable) if is_frozen else Path(sys.argv[0])

        if not is_frozen:
            msg = f"Tải xuống thành công file: {temp_file.name}\n\nDo bạn đang chạy mã nguồn Python trực tiếp (.py), hệ thống sẽ KHÔNG tự động ghi đè để bảo vệ mã nguồn của bạn."
            messagebox.showinfo("Cập nhật thành công (Chế độ phát triển)", msg, parent=self.root)
            self.status_var.set("Đã tải xong bản cập nhật (Python Mode).")
            return

        # Viết kịch bản update.bat để ghi đè & khởi động lại exe
        bat_path = current_exe.parent / "update.bat"
        try:
            bat_content = f"""@echo off
timeout /t 2 /nobreak > NUL
copy /y "{temp_file}" "{current_exe}" > NUL
del "{temp_file}" > NUL
start "" "{current_exe}"
del "%~f0"
"""
            bat_path.write_text(bat_content, encoding="utf-8")
            
            # Khởi chạy script bat độc lập không đồng bộ
            creationflags = 0
            if hasattr(subprocess, "CREATE_NEW_CONSOLE"):
                creationflags |= subprocess.CREATE_NEW_CONSOLE
            if hasattr(subprocess, "DETACHED_PROCESS"):
                creationflags |= subprocess.DETACHED_PROCESS
            
            subprocess.Popen(
                [str(bat_path)],
                shell=True,
                creationflags=creationflags
            )
            
            # Thoát ứng dụng lập tức
            self.root.destroy()
            sys.exit(0)
        except Exception as e:
            self.log(f"Lỗi thực hiện cập nhật tự động: {e}")
            messagebox.showerror(
                "Lỗi cập nhật", 
                f"Không thể tự động ghi đè file.\nVui lòng tự đổi tên và thay thế bằng file: {temp_file.name}\nChi tiết: {e}",
                parent=self.root
            )



def main():
    # Must be called BEFORE creating any windows to avoid coordinate mismatch
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor DPI Aware
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # System DPI Aware fallback
        except Exception:
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
