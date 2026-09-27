"""
Auto Clicker
============
Two modes:
  - Image match: loads a target image, searches a screen region for it, and
    clicks the best match above your confidence threshold.
  - Fixed point: click a spot on screen once to set it, then clicks that
    exact spot repeatedly at a clicks-per-second rate you set. No image
    needed - this is a classic auto-clicker.

Global hotkeys (work even when this window isn't focused) default to
F1 = Start, F2 = Stop, and can be reassigned from the UI.

Move your mouse to any screen corner at any time to trigger PyAutoGUI's
built-in fail-safe and immediately abort (this is a safety feature, don't
disable it).

Setup:
    pip install -r requirements.txt
    python auto_clicker.py

macOS: System Settings -> Privacy & Security -> Accessibility and
       Screen Recording -> enable your terminal/Python. Also enable
       Accessibility for global hotkeys to work.
Linux: needs `scrot` or `gnome-screenshot` installed for screenshots
       (sudo apt install scrot). Global hotkeys need to run as root
       on some distros due to how the `keyboard` library hooks input.
Windows: if hotkeys don't respond, try running as Administrator.
"""

import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
import keyboard
import numpy as np
import pyautogui
from PIL import Image, ImageTk

pyautogui.FAILSAFE = True  # move mouse to a screen corner to abort


class RegionSelector:
    """Fullscreen semi-transparent overlay for drag-selecting a screen region."""

    def __init__(self, root, on_done):
        self.on_done = on_done
        self.start_x = self.start_y = None
        self.rect = None

        self.overlay = tk.Toplevel(root)
        self.overlay.attributes("-fullscreen", True)
        self.overlay.attributes("-alpha", 0.30)
        self.overlay.attributes("-topmost", True)
        self.overlay.configure(bg="black")

        self.canvas = tk.Canvas(self.overlay, cursor="cross", bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        tk.Label(
            self.overlay,
            text="Click and drag to select the region the clicker should search. Press Esc to cancel.",
            fg="white", bg="black", font=("Segoe UI", 14),
        ).place(relx=0.5, rely=0.05, anchor="n")

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.overlay.bind("<Escape>", lambda e: self._cancel())

    def _on_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y, outline="red", width=2
        )

    def _on_drag(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def _on_release(self, event):
        x1, y1, x2, y2 = self.start_x, self.start_y, event.x, event.y
        left, top = min(x1, x2), min(y1, y2)
        width, height = abs(x2 - x1), abs(y2 - y1)
        self.overlay.destroy()
        if width > 2 and height > 2:
            self.on_done((left, top, width, height))
        else:
            self.on_done(None)

    def _cancel(self):
        self.overlay.destroy()
        self.on_done(None)


class PointSelector:
    """Fullscreen overlay for picking a single screen coordinate with a click."""

    def __init__(self, root, on_done):
        self.on_done = on_done
        self.overlay = tk.Toplevel(root)
        self.overlay.attributes("-fullscreen", True)
        self.overlay.attributes("-alpha", 0.30)
        self.overlay.attributes("-topmost", True)
        self.overlay.configure(bg="black")

        self.canvas = tk.Canvas(self.overlay, cursor="crosshair", bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        tk.Label(
            self.overlay,
            text="Click the exact spot you want the clicker to target. Press Esc to cancel.",
            fg="white", bg="black", font=("Segoe UI", 14),
        ).place(relx=0.5, rely=0.05, anchor="n")

        self.canvas.bind("<Button-1>", self._on_click)
        self.overlay.bind("<Escape>", lambda e: self._cancel())

    def _on_click(self, event):
        x, y = event.x_root, event.y_root
        self.overlay.destroy()
        self.on_done((x, y))

    def _cancel(self):
        self.overlay.destroy()
        self.on_done(None)


class AutoClickerApp:
    def __init__(self, root):
        self.root = root
        root.title("Auto Clicker")
        root.resizable(False, False)

        # image-match state
        self.template = None
        self.template_path = None
        self.region = None

        # fixed-point state
        self.point = None

        self.running = False
        self.worker = None
        self.click_count = 0

        self.mode = tk.StringVar(value="image")
        self.start_hotkey = tk.StringVar(value="f1")
        self.stop_hotkey = tk.StringVar(value="f2")
        self._start_hotkey_handle = None
        self._stop_hotkey_handle = None

        pad = {"padx": 10, "pady": 6}

        # --- Mode switch ---
        mode_frame = ttk.LabelFrame(root, text="Mode")
        mode_frame.pack(fill="x", **pad)
        ttk.Radiobutton(mode_frame, text="Image match (search for a picture)", variable=self.mode,
                         value="image", command=self._refresh_mode).pack(anchor="w", padx=8, pady=2)
        ttk.Radiobutton(mode_frame, text="Fixed point (click a set spot, no image needed)", variable=self.mode,
                         value="point", command=self._refresh_mode).pack(anchor="w", padx=8, pady=2)

        # --- Image mode frame ---
        self.image_frame = ttk.Frame(root)

        f1 = ttk.LabelFrame(self.image_frame, text="Target image (what to click)")
        f1.pack(fill="x", **pad)
        self.target_label = ttk.Label(f1, text="No image loaded")
        self.target_label.pack(side="left", padx=8, pady=8)
        self.thumb_label = ttk.Label(f1)
        self.thumb_label.pack(side="left", padx=8)
        ttk.Button(f1, text="Load Image...", command=self.load_template).pack(side="right", padx=8)

        f2 = ttk.LabelFrame(self.image_frame, text="Search region (optional)")
        f2.pack(fill="x", **pad)
        self.region_label = ttk.Label(f2, text="Full screen (no region set)")
        self.region_label.pack(side="left", padx=8, pady=8)
        ttk.Button(f2, text="Select Region...", command=self.select_region).pack(side="right", padx=8)
        ttk.Button(f2, text="Clear", command=self.clear_region).pack(side="right", padx=4)

        f3 = ttk.LabelFrame(self.image_frame, text="Match settings")
        f3.pack(fill="x", **pad)
        ttk.Label(f3, text="Match confidence (0.5-0.99):").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.confidence = tk.DoubleVar(value=0.85)
        ttk.Entry(f3, textvariable=self.confidence, width=8).grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(f3, text="Check interval (seconds):").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        self.interval = tk.DoubleVar(value=1.0)
        ttk.Entry(f3, textvariable=self.interval, width=8).grid(row=1, column=1, sticky="w", pady=4)

        # --- Point mode frame ---
        self.point_frame = ttk.Frame(root)

        f4 = ttk.LabelFrame(self.point_frame, text="Click point")
        f4.pack(fill="x", **pad)
        self.point_label = ttk.Label(f4, text="No point set")
        self.point_label.pack(side="left", padx=8, pady=8)
        ttk.Button(f4, text="Set Click Point...", command=self.select_point).pack(side="right", padx=8)

        f5 = ttk.LabelFrame(self.point_frame, text="Speed")
        f5.pack(fill="x", **pad)
        ttk.Label(f5, text="Clicks per second:").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.cps = tk.DoubleVar(value=5.0)
        ttk.Entry(f5, textvariable=self.cps, width=8).grid(row=0, column=1, sticky="w", pady=4)

        # --- Shared settings: click limit ---
        f6 = ttk.LabelFrame(root, text="Limit")
        f6.pack(fill="x", **pad)
        ttk.Label(f6, text="Stop after N clicks (0 = unlimited):").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.max_clicks = tk.IntVar(value=0)
        ttk.Entry(f6, textvariable=self.max_clicks, width=8).grid(row=0, column=1, sticky="w", pady=4)

        # --- Hotkeys ---
        f7 = ttk.LabelFrame(root, text="Hotkeys (work even when this window isn't focused)")
        f7.pack(fill="x", **pad)
        ttk.Label(f7, text="Start:").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.start_key_label = ttk.Label(f7, text=self.start_hotkey.get().upper(), width=10)
        self.start_key_label.grid(row=0, column=1, sticky="w")
        ttk.Button(f7, text="Change", command=lambda: self.change_hotkey("start")).grid(row=0, column=2, padx=8)

        ttk.Label(f7, text="Stop:").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        self.stop_key_label = ttk.Label(f7, text=self.stop_hotkey.get().upper(), width=10)
        self.stop_key_label.grid(row=1, column=1, sticky="w")
        ttk.Button(f7, text="Change", command=lambda: self.change_hotkey("stop")).grid(row=1, column=2, padx=8)

        # --- Controls ---
        f8 = ttk.Frame(root)
        f8.pack(fill="x", **pad)
        self.start_btn = ttk.Button(f8, text="Start", command=self.start)
        self.start_btn.pack(side="left", padx=8)
        self.stop_btn = ttk.Button(f8, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=8)

        self.status = tk.StringVar(value="Idle. Choose a mode above to begin.")
        ttk.Label(root, textvariable=self.status, wraplength=420).pack(fill="x", padx=10, pady=(0, 10))

        self._refresh_mode()
        self.register_hotkeys()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- mode switching ----------

    def _refresh_mode(self):
        if self.mode.get() == "image":
            self.point_frame.pack_forget()
            self.image_frame.pack(fill="x")
        else:
            self.image_frame.pack_forget()
            self.point_frame.pack(fill="x")

    # ---------- image mode actions ----------

    def load_template(self):
        path = filedialog.askopenfilename(
            title="Select target image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")],
        )
        if not path:
            return
        img = cv2.imread(path)
        if img is None:
            messagebox.showerror("Error", "Could not read that image file.")
            return
        self.template = img
        self.template_path = path
        self.target_label.config(text=path.split("/")[-1].split("\\")[-1])

        pil_img = Image.open(path)
        pil_img.thumbnail((48, 48))
        self.thumb_img = ImageTk.PhotoImage(pil_img)
        self.thumb_label.config(image=self.thumb_img)
        self.status.set("Target image loaded.")

    def select_region(self):
        self.root.iconify()
        self.root.after(300, lambda: RegionSelector(self.root, self._on_region_selected))

    def _on_region_selected(self, region):
        self.root.deiconify()
        if region:
            self.region = region
            self.region_label.config(text=f"Region: x={region[0]}, y={region[1]}, w={region[2]}, h={region[3]}")
        else:
            self.status.set("Region selection cancelled.")

    def clear_region(self):
        self.region = None
        self.region_label.config(text="Full screen (no region set)")

    # ---------- point mode actions ----------

    def select_point(self):
        self.root.iconify()
        self.root.after(300, lambda: PointSelector(self.root, self._on_point_selected))

    def _on_point_selected(self, point):
        self.root.deiconify()
        if point:
            self.point = point
            self.point_label.config(text=f"Point: ({point[0]}, {point[1]})")
            self.status.set("Click point set.")
        else:
            self.status.set("Point selection cancelled.")

    # ---------- hotkeys ----------

    def register_hotkeys(self):
        for handle in (self._start_hotkey_handle, self._stop_hotkey_handle):
            if handle:
                try:
                    keyboard.remove_hotkey(handle)
                except (KeyError, ValueError):
                    pass
        try:
            self._start_hotkey_handle = keyboard.add_hotkey(self.start_hotkey.get(), self.start)
            self._stop_hotkey_handle = keyboard.add_hotkey(self.stop_hotkey.get(), self.stop)
        except Exception as e:
            self.status.set(f"Could not register hotkeys: {e}")

    def change_hotkey(self, which):
        dialog = tk.Toplevel(self.root)
        dialog.title("Set hotkey")
        dialog.geometry("280x100")
        dialog.resizable(False, False)
        tk.Label(dialog, text="Press the key you want to use...", font=("Segoe UI", 11)).pack(expand=True, pady=25)
        dialog.grab_set()
        dialog.attributes("-topmost", True)

        def capture():
            try:
                new_key = keyboard.read_hotkey(suppress=False)
            except Exception:
                new_key = None
            self.root.after(0, lambda: self._apply_hotkey(which, new_key, dialog))

        threading.Thread(target=capture, daemon=True).start()

    def _apply_hotkey(self, which, new_key, dialog):
        try:
            dialog.destroy()
        except tk.TclError:
            pass
        if not new_key:
            return
        if which == "start":
            self.start_hotkey.set(new_key)
            self.start_key_label.config(text=new_key.upper())
        else:
            self.stop_hotkey.set(new_key)
            self.stop_key_label.config(text=new_key.upper())
        self.register_hotkeys()
        self.status.set(f"{'Start' if which == 'start' else 'Stop'} hotkey set to {new_key.upper()}.")

    # ---------- run control ----------

    def start(self):
        if self.running:
            return
        mode = self.mode.get()
        if mode == "image":
            if self.template is None:
                messagebox.showwarning("No target", "Load a target image first.")
                return
            try:
                conf = float(self.confidence.get())
                float(self.interval.get())
            except (tk.TclError, ValueError):
                messagebox.showwarning("Invalid settings", "Confidence and interval must be numbers.")
                return
            if not (0 < conf <= 1):
                messagebox.showwarning("Invalid settings", "Confidence must be between 0 and 1.")
                return
            loop_fn = self._loop_image
        else:
            if self.point is None:
                messagebox.showwarning("No point", "Set a click point first.")
                return
            try:
                float(self.cps.get())
            except (tk.TclError, ValueError):
                messagebox.showwarning("Invalid settings", "Clicks per second must be a number.")
                return
            loop_fn = self._loop_point

        self.running = True
        self.click_count = 0
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.worker = threading.Thread(target=loop_fn, daemon=True)
        self.worker.start()

    def stop(self):
        if not self.running:
            return
        self.running = False
        self.root.after(0, lambda: (self.start_btn.config(state="normal"), self.stop_btn.config(state="disabled")))
        self.status.set(f"Stopped. Total clicks: {self.click_count}")

    # ---------- worker loops ----------

    def _loop_image(self):
        th, tw = self.template.shape[:2]
        limit = int(self.max_clicks.get() or 0)

        while self.running:
            try:
                region = self.region
                shot = pyautogui.screenshot(region=region) if region else pyautogui.screenshot()
                screen = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)

                result = cv2.matchTemplate(screen, self.template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)

                if max_val >= float(self.confidence.get()):
                    cx = max_loc[0] + tw // 2
                    cy = max_loc[1] + th // 2
                    if region:
                        cx += region[0]
                        cy += region[1]
                    pyautogui.click(cx, cy)
                    self.click_count += 1
                    self._set_status(f"Clicked ({cx},{cy}) - confidence {max_val:.2f} - total {self.click_count}")

                    if limit and self.click_count >= limit:
                        self._set_status(f"Reached click limit ({limit}). Stopping.")
                        self.running = False
                        self.root.after(0, self.stop)
                        break
                else:
                    self._set_status(f"No match this check (best score {max_val:.2f})")

            except pyautogui.FailSafeException:
                self._set_status("Fail-safe triggered (mouse hit a corner). Stopped.")
                self.running = False
                self.root.after(0, self.stop)
                break
            except Exception as e:
                self._set_status(f"Error: {e}")

            time.sleep(max(0.05, float(self.interval.get())))

    def _loop_point(self):
        limit = int(self.max_clicks.get() or 0)

        while self.running:
            interval = 0.5
            try:
                cps = max(0.1, float(self.cps.get()))
                interval = 1.0 / cps
                pyautogui.click(self.point[0], self.point[1])
                self.click_count += 1
                self._set_status(f"Clicked ({self.point[0]},{self.point[1]}) - total {self.click_count}")

                if limit and self.click_count >= limit:
                    self._set_status(f"Reached click limit ({limit}). Stopping.")
                    self.running = False
                    self.root.after(0, self.stop)
                    break

            except pyautogui.FailSafeException:
                self._set_status("Fail-safe triggered (mouse hit a corner). Stopped.")
                self.running = False
                self.root.after(0, self.stop)
                break
            except Exception as e:
                self._set_status(f"Error: {e}")

            time.sleep(interval)

    def _set_status(self, text):
        self.root.after(0, lambda: self.status.set(text))

    def _on_close(self):
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = AutoClickerApp(root)
    root.mainloop()
