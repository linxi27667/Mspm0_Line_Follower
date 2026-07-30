#!/usr/bin/env python3
"""Windows GUI for the writer drawing converter."""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageTk

import draw_to_gcode as core


APP_TITLE = "写字机画图转换器"
WINDOW_SIZE = "1040x760"
PREVIEW_SIZE = (650, 540)
BACKGROUND = "#f3f5f4"
SURFACE = "#ffffff"
TEXT = "#202522"
MUTED = "#66706a"
ACCENT = "#176b4d"
ACCENT_ACTIVE = "#0f543b"
BLUE = "#315ea8"
WARNING = "#a34c2d"


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def format_seconds(value: float) -> str:
    seconds = max(0, round(value))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}小时{minutes}分"
    if minutes:
        return f"{minutes}分{seconds}秒"
    return f"{seconds}秒"


class ConverterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.minsize(940, 680)
        self.root.configure(background=BACKGROUND)
        self._preview_photo: ImageTk.PhotoImage | None = None
        self._last_output_directory: Path | None = None
        self._busy = False

        self.input_path = tk.StringVar()
        self.output_directory = tk.StringVar()
        self.mode = tk.StringVar(value="outline")
        self.left_mm = tk.StringVar(value=f"{core.DEFAULT_LEFT_MM:g}")
        self.bottom_mm = tk.StringVar(value=f"{core.DEFAULT_BOTTOM_MM:g}")
        self.width_mm = tk.StringVar(value=f"{core.DEFAULT_WIDTH_MM:g}")
        self.height_mm = tk.StringVar(value=f"{core.DEFAULT_HEIGHT_MM:g}")
        self.rotate_deg = tk.StringVar(value="0")
        self.threshold = tk.StringVar(value="auto")
        self.invert = tk.BooleanVar(value=False)
        self.blur_px = tk.StringVar(value="3")
        self.canny_low = tk.StringVar(value="80")
        self.canny_high = tk.StringVar(value="180")
        self.hatch_spacing_mm = tk.StringVar(value="1.0")
        self.simplify_mm = tk.StringVar(value="0.15")
        self.min_path_mm = tk.StringVar(value="0.8")
        self.approach_mm = tk.StringVar(value="5.0")
        self.feed_mm_min = tk.StringVar(value="300")
        self.optimize = tk.BooleanVar(value=True)
        self.max_paths = tk.StringVar(value="2000")
        self.status_text = tk.StringVar(value="等待选择图片")
        self.result_text = tk.StringVar(value="")

        self._configure_styles()
        self._build_ui()
        self._show_placeholder("选择 PNG、JPG 或 SVG")
        self.root.bind("<Control-o>", lambda _event: self.choose_input())
        self.root.bind("<Control-O>", lambda _event: self.choose_input())
        self.root.bind("<Return>", lambda _event: self.start_conversion())

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=("Microsoft YaHei UI", 10), foreground=TEXT)
        style.configure("TFrame", background=BACKGROUND)
        style.configure("Surface.TFrame", background=SURFACE)
        style.configure("TLabel", background=BACKGROUND, foreground=TEXT)
        style.configure("Surface.TLabel", background=SURFACE, foreground=TEXT)
        style.configure("Muted.TLabel", background=BACKGROUND, foreground=MUTED)
        style.configure("Profile.TLabel", background="#e7eee9", foreground="#274537", padding=(10, 7))
        style.configure("TButton", padding=(12, 8), background="#e7eae8", foreground=TEXT)
        style.map("TButton", background=[("active", "#dce1de")])
        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff", padding=(16, 10))
        style.map(
            "Accent.TButton",
            background=[("active", ACCENT_ACTIVE), ("disabled", "#9db5aa")],
            foreground=[("disabled", "#eef3f0")],
        )
        style.configure("Mode.Toolbutton", padding=(13, 7), background="#e8ebe9")
        style.map(
            "Mode.Toolbutton",
            background=[("selected", BLUE), ("active", "#d9dfdc")],
            foreground=[("selected", "#ffffff")],
        )
        style.configure("TNotebook", background=BACKGROUND, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 8), background="#e6e9e7")
        style.map("TNotebook.Tab", background=[("selected", SURFACE)])
        style.configure("TEntry", fieldbackground="#ffffff", padding=6)
        style.configure("TSpinbox", fieldbackground="#ffffff", padding=5)
        style.configure("Horizontal.TSeparator", background="#d7dcd9")

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=(22, 18, 22, 16))
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text=APP_TITLE,
            font=("Microsoft YaHei UI", 19, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text=(
                f"固件 {core.REQUIRED_FIRMWARE_ID}  |  映射 {core.REQUIRED_PAPER_MAP_ID}  |  "
                "安全区 X25..185 / Y130..235 mm"
            ),
            style="Profile.TLabel",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))

        file_rows = ttk.Frame(outer, padding=(0, 15, 0, 13))
        file_rows.grid(row=1, column=0, sticky="ew")
        file_rows.columnconfigure(1, weight=1)
        ttk.Label(file_rows, text="输入文件", width=9).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(file_rows, textvariable=self.input_path, state="readonly").grid(
            row=0, column=1, sticky="ew", padx=(0, 8), pady=4
        )
        ttk.Button(file_rows, text="选择图片", command=self.choose_input).grid(
            row=0, column=2, pady=4
        )
        ttk.Label(file_rows, text="输出目录", width=9).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(file_rows, textvariable=self.output_directory, state="readonly").grid(
            row=1, column=1, sticky="ew", padx=(0, 8), pady=4
        )
        ttk.Button(file_rows, text="选择目录", command=self.choose_output_directory).grid(
            row=1, column=2, pady=4
        )

        ttk.Separator(outer).grid(row=2, column=0, sticky="ew")

        content = ttk.Frame(outer, padding=(0, 15, 0, 12))
        content.grid(row=3, column=0, sticky="nsew")
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2)

        preview_surface = ttk.Frame(content, style="Surface.TFrame", padding=10)
        preview_surface.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        preview_surface.rowconfigure(0, weight=1)
        preview_surface.columnconfigure(0, weight=1)
        self.preview_label = ttk.Label(
            preview_surface,
            style="Surface.TLabel",
            anchor="center",
        )
        self.preview_label.grid(row=0, column=0, sticky="nsew")

        settings = ttk.Frame(content)
        settings.grid(row=0, column=1, sticky="nsew")
        settings.columnconfigure(0, weight=1)
        settings.rowconfigure(2, weight=1)

        ttk.Label(settings, text="轨迹模式", font=("Microsoft YaHei UI", 11, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 7)
        )
        mode_row = ttk.Frame(settings)
        mode_row.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        for column, (value, label) in enumerate(
            (("outline", "轮廓"), ("edge", "边缘"), ("hatch", "排线"))
        ):
            mode_row.columnconfigure(column, weight=1)
            ttk.Radiobutton(
                mode_row,
                text=label,
                value=value,
                variable=self.mode,
                style="Mode.Toolbutton",
                command=self._update_mode_state,
            ).grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 3, 0))

        notebook = ttk.Notebook(settings)
        notebook.grid(row=2, column=0, sticky="nsew")
        layout_tab = ttk.Frame(notebook, style="Surface.TFrame", padding=14)
        path_tab = ttk.Frame(notebook, style="Surface.TFrame")
        notebook.add(layout_tab, text="纸面排版")
        notebook.add(path_tab, text="轨迹参数")
        self._build_layout_tab(layout_tab)
        self._build_path_tab(path_tab)

        action = ttk.Frame(outer)
        action.grid(row=4, column=0, sticky="ew")
        action.columnconfigure(1, weight=1)
        self.generate_button = ttk.Button(
            action,
            text="生成 G-code 和矢量图",
            style="Accent.TButton",
            command=self.start_conversion,
        )
        self.generate_button.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 14))
        ttk.Label(action, textvariable=self.status_text).grid(row=0, column=1, sticky="w")
        ttk.Label(action, textvariable=self.result_text, style="Muted.TLabel").grid(
            row=1, column=1, sticky="w"
        )
        self.open_button = ttk.Button(
            action,
            text="打开输出目录",
            command=self.open_output_directory,
            state="disabled",
        )
        self.open_button.grid(row=0, column=2, rowspan=2, sticky="e")

    def _build_layout_tab(self, tab: ttk.Frame) -> None:
        tab.columnconfigure(1, weight=1)
        controls = (
            ("左边 X (mm)", self.left_mm, 25.0, 185.0, 1.0),
            ("下边 Y (mm)", self.bottom_mm, 130.0, 235.0, 1.0),
            ("最大宽度 (mm)", self.width_mm, 5.0, 160.0, 1.0),
            ("最大高度 (mm)", self.height_mm, 5.0, 105.0, 1.0),
            ("顺时针旋转 (°)", self.rotate_deg, -360.0, 360.0, 1.0),
        )
        for row, (label, variable, minimum, maximum, increment) in enumerate(controls):
            ttk.Label(tab, text=label, style="Surface.TLabel").grid(
                row=row, column=0, sticky="w", pady=6
            )
            ttk.Spinbox(
                tab,
                textvariable=variable,
                from_=minimum,
                to=maximum,
                increment=increment,
                width=13,
            ).grid(row=row, column=1, sticky="e", pady=6)
        ttk.Separator(tab).grid(row=len(controls), column=0, columnspan=2, sticky="ew", pady=12)
        ttk.Label(
            tab,
            text="输出：G-code / A4矢量SVG / 路径预览 / 安全清单",
            style="Surface.TLabel",
            wraplength=300,
        ).grid(row=len(controls) + 1, column=0, columnspan=2, sticky="w")

    def _build_path_tab(self, tab: ttk.Frame) -> None:
        tab.rowconfigure(0, weight=1)
        tab.columnconfigure(0, weight=1)
        path_canvas = tk.Canvas(
            tab,
            background=SURFACE,
            borderwidth=0,
            highlightthickness=0,
        )
        path_scrollbar = ttk.Scrollbar(
            tab,
            orient="vertical",
            command=path_canvas.yview,
        )
        path_canvas.configure(yscrollcommand=path_scrollbar.set)
        path_canvas.grid(row=0, column=0, sticky="nsew")
        path_scrollbar.grid(row=0, column=1, sticky="ns")

        controls = ttk.Frame(path_canvas, style="Surface.TFrame", padding=14)
        controls.columnconfigure(1, weight=1)
        controls_window = path_canvas.create_window(
            (0, 0),
            window=controls,
            anchor="nw",
        )

        def update_scroll_region(_event: tk.Event) -> None:
            path_canvas.configure(scrollregion=path_canvas.bbox("all"))

        def fit_controls_to_canvas(event: tk.Event) -> None:
            path_canvas.itemconfigure(controls_window, width=event.width)

        def scroll_path_parameters(event: tk.Event) -> str | None:
            if not event.delta:
                return None
            direction = -1 if event.delta > 0 else 1
            path_canvas.yview_scroll(direction * 3, "units")
            return "break"

        def bind_mousewheel(widget: tk.Misc) -> None:
            widget.bind("<MouseWheel>", scroll_path_parameters, add="+")
            for child in widget.winfo_children():
                bind_mousewheel(child)

        controls.bind("<Configure>", update_scroll_region)
        path_canvas.bind("<Configure>", fit_controls_to_canvas)

        self.threshold_label = ttk.Label(controls, text="黑白阈值", style="Surface.TLabel")
        self.threshold_label.grid(row=0, column=0, sticky="w", pady=5)
        self.threshold_entry = ttk.Entry(controls, textvariable=self.threshold, width=13)
        self.threshold_entry.grid(row=0, column=1, sticky="e", pady=5)

        self.blur_label = ttk.Label(controls, text="边缘模糊 (px)", style="Surface.TLabel")
        self.blur_label.grid(row=1, column=0, sticky="w", pady=5)
        self.blur_entry = ttk.Spinbox(controls, textvariable=self.blur_px, from_=0, to=15, increment=2, width=13)
        self.blur_entry.grid(row=1, column=1, sticky="e", pady=5)

        self.canny_low_label = ttk.Label(controls, text="Canny 低阈值", style="Surface.TLabel")
        self.canny_low_label.grid(row=2, column=0, sticky="w", pady=5)
        self.canny_low_entry = ttk.Spinbox(controls, textvariable=self.canny_low, from_=0, to=254, width=13)
        self.canny_low_entry.grid(row=2, column=1, sticky="e", pady=5)
        self.canny_high_label = ttk.Label(controls, text="Canny 高阈值", style="Surface.TLabel")
        self.canny_high_label.grid(row=3, column=0, sticky="w", pady=5)
        self.canny_high_entry = ttk.Spinbox(controls, textvariable=self.canny_high, from_=1, to=255, width=13)
        self.canny_high_entry.grid(row=3, column=1, sticky="e", pady=5)

        self.hatch_label = ttk.Label(controls, text="排线间距 (mm)", style="Surface.TLabel")
        self.hatch_label.grid(row=4, column=0, sticky="w", pady=5)
        self.hatch_entry = ttk.Spinbox(
            controls, textvariable=self.hatch_spacing_mm, from_=0.2, to=10.0, increment=0.1, width=13
        )
        self.hatch_entry.grid(row=4, column=1, sticky="e", pady=5)

        common = (
            ("简化公差 (mm)", self.simplify_mm, 0.0, 5.0, 0.05),
            ("最短路径 (mm)", self.min_path_mm, 0.1, 50.0, 0.1),
            ("落笔预走 (mm)", self.approach_mm, 0.0, 20.0, 0.5),
            ("速度 F (mm/min)", self.feed_mm_min, 30.0, 1200.0, 10.0),
            ("最大路径数", self.max_paths, 1, 10000, 100),
        )
        for offset, (label, variable, minimum, maximum, increment) in enumerate(common, start=5):
            ttk.Label(controls, text=label, style="Surface.TLabel").grid(
                row=offset, column=0, sticky="w", pady=5
            )
            ttk.Spinbox(
                controls,
                textvariable=variable,
                from_=minimum,
                to=maximum,
                increment=increment,
                width=13,
            ).grid(row=offset, column=1, sticky="e", pady=5)

        check_row = 10
        ttk.Checkbutton(controls, text="反转前景", variable=self.invert).grid(
            row=check_row, column=0, sticky="w", pady=(10, 4)
        )
        ttk.Checkbutton(controls, text="优化空走顺序", variable=self.optimize).grid(
            row=check_row, column=1, sticky="e", pady=(10, 4)
        )
        bind_mousewheel(controls)
        path_canvas.bind("<MouseWheel>", scroll_path_parameters, add="+")
        self._update_mode_state()

    def _update_mode_state(self) -> None:
        mode = self.mode.get()
        threshold_state = "normal" if mode != "edge" else "disabled"
        edge_state = "normal" if mode == "edge" else "disabled"
        hatch_state = "normal" if mode == "hatch" else "disabled"
        self.threshold_entry.configure(state=threshold_state)
        self.blur_entry.configure(state=edge_state)
        self.canny_low_entry.configure(state=edge_state)
        self.canny_high_entry.configure(state=edge_state)
        self.hatch_entry.configure(state=hatch_state)

    def choose_input(self) -> None:
        selected = filedialog.askopenfilename(
            title="选择图片或 SVG",
            filetypes=(
                ("支持的图片", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.svg"),
                ("SVG 矢量图", "*.svg"),
                ("所有文件", "*.*"),
            ),
        )
        if not selected:
            return
        path = Path(selected).resolve()
        self.input_path.set(str(path))
        if not self.output_directory.get():
            self.output_directory.set(str(path.parent / "writer_output"))
        if path.suffix.lower() == ".svg":
            self.mode.set("outline")
            self._update_mode_state()
            self._show_placeholder("SVG\n转换后显示纸面路径")
        else:
            self._show_image(path)
        self.status_text.set("文件已选择")
        self.result_text.set("")

    def choose_output_directory(self) -> None:
        selected = filedialog.askdirectory(
            title="选择输出目录",
            initialdir=self.output_directory.get() or None,
        )
        if selected:
            self.output_directory.set(str(Path(selected).resolve()))

    def _show_placeholder(self, text: str) -> None:
        image = Image.new("RGB", PREVIEW_SIZE, "#ffffff")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, PREVIEW_SIZE[0] - 1, PREVIEW_SIZE[1] - 1), outline="#d7dcd9", width=2)
        try:
            font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 24)
        except OSError:
            font = ImageFont.load_default()
        box = draw.multiline_textbbox((0, 0), text, font=font, spacing=9, align="center")
        x = (PREVIEW_SIZE[0] - (box[2] - box[0])) / 2
        y = (PREVIEW_SIZE[1] - (box[3] - box[1])) / 2
        draw.multiline_text((x, y), text, fill=MUTED, font=font, spacing=9, align="center")
        self._set_preview(image)

    def _show_image(self, path: Path) -> None:
        try:
            with Image.open(path) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                image = ImageOps.contain(image, PREVIEW_SIZE, Image.Resampling.LANCZOS)
        except (OSError, ValueError) as exc:
            messagebox.showerror(APP_TITLE, f"无法预览图片：{exc}")
            return
        canvas = Image.new("RGB", PREVIEW_SIZE, "#ffffff")
        canvas.paste(
            image,
            ((PREVIEW_SIZE[0] - image.width) // 2, (PREVIEW_SIZE[1] - image.height) // 2),
        )
        self._set_preview(canvas)

    def _set_preview(self, image: Image.Image) -> None:
        self._preview_photo = ImageTk.PhotoImage(image)
        self.preview_label.configure(image=self._preview_photo)

    def _output_paths(self) -> tuple[Path, Path, Path, Path]:
        input_path = Path(self.input_path.get()).resolve()
        directory = Path(self.output_directory.get()).resolve()
        stem = f"DRAW_{core.safe_stem(input_path)}_V1"
        return (
            directory / f"{stem}.gcode",
            directory / f"{stem}.preview.png",
            directory / f"{stem}.vector.svg",
            directory / f"{stem}.json",
        )

    def _converter_arguments(self, force: bool) -> list[str]:
        output, preview, vector, manifest = self._output_paths()
        arguments = [
            self.input_path.get(),
            "--mode",
            self.mode.get(),
            "--output",
            str(output),
            "--preview",
            str(preview),
            "--vector",
            str(vector),
            "--manifest",
            str(manifest),
            "--left-mm",
            self.left_mm.get(),
            "--bottom-mm",
            self.bottom_mm.get(),
            "--width-mm",
            self.width_mm.get(),
            "--height-mm",
            self.height_mm.get(),
            "--rotate-deg",
            self.rotate_deg.get(),
            "--threshold",
            self.threshold.get(),
            "--blur-px",
            self.blur_px.get(),
            "--canny-low",
            self.canny_low.get(),
            "--canny-high",
            self.canny_high.get(),
            "--hatch-spacing-mm",
            self.hatch_spacing_mm.get(),
            "--simplify-mm",
            self.simplify_mm.get(),
            "--min-path-mm",
            self.min_path_mm.get(),
            "--approach-mm",
            self.approach_mm.get(),
            "--feed-mm-min",
            self.feed_mm_min.get(),
            "--max-paths",
            self.max_paths.get(),
        ]
        if self.invert.get():
            arguments.append("--invert")
        if not self.optimize.get():
            arguments.append("--no-optimize")
        if force:
            arguments.append("--force")
        return arguments

    def start_conversion(self) -> None:
        if self._busy:
            return
        if not self.input_path.get():
            messagebox.showwarning(APP_TITLE, "请选择输入图片或 SVG。")
            return
        if not self.output_directory.get():
            messagebox.showwarning(APP_TITLE, "请选择输出目录。")
            return
        try:
            outputs = self._output_paths()
        except (OSError, ValueError) as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        existing = [path for path in outputs if path.exists()]
        force = False
        if existing:
            force = messagebox.askyesno(
                APP_TITLE,
                f"输出文件已存在：\n{existing[0].name}\n\n是否覆盖本组输出？",
            )
            if not force:
                return

        self._busy = True
        self.generate_button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.status_text.set("正在转换和执行安全审计...")
        self.result_text.set("")
        arguments = self._converter_arguments(force)
        worker = threading.Thread(
            target=self._run_conversion,
            args=(arguments,),
            daemon=True,
        )
        worker.start()

    def _run_conversion(self, arguments: list[str]) -> None:
        try:
            parsed = core.arguments(arguments)
            config = core.config_from_arguments(parsed)
            manifest = core.convert(config)
        except SystemExit:
            error = core.ConversionError("参数格式不正确，请检查数值输入。")
            self.root.after(0, lambda error=error: self._conversion_failed(error))
            return
        except Exception as exc:
            self.root.after(0, lambda error=exc: self._conversion_failed(error))
            return
        self.root.after(0, lambda: self._conversion_finished(config, manifest))

    def _conversion_failed(self, error: Exception) -> None:
        self._busy = False
        self.generate_button.configure(state="normal")
        self.status_text.set("转换失败")
        messagebox.showerror(APP_TITLE, str(error))

    def _conversion_finished(
        self,
        config: core.ConversionConfig,
        manifest: dict[str, object],
    ) -> None:
        self._busy = False
        self.generate_button.configure(state="normal")
        self.open_button.configure(state="normal")
        self._last_output_directory = config.output_path.parent
        safety = manifest["safety"]
        minimum_margin = safety["drawing_sequence"]["minimum_joint_margin_deg"]
        minimum_seconds = safety["estimated_minimum_seconds_excluding_rapid"]
        self.status_text.set("生成完成：G-code、矢量 SVG、预览和安全清单")
        self.result_text.set(
            f"{safety['path_count']} 条路径  |  {safety['point_count']} 个点  |  "
            f"画线 {safety['draw_length_mm'] / 1000.0:.2f} m  |  "
            f"最低余量 {minimum_margin:.1f}°  |  不含空走约 {format_seconds(minimum_seconds)}"
        )
        self._show_image(config.preview_path)

    def open_output_directory(self) -> None:
        if self._last_output_directory is None:
            return
        self._last_output_directory.mkdir(parents=True, exist_ok=True)
        os.startfile(self._last_output_directory)


def main() -> int:
    if len(sys.argv) > 1:
        return core.main(sys.argv[1:])
    enable_dpi_awareness()
    root = tk.Tk()
    ConverterApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
