"""Build host app to standalone exe."""
from __future__ import annotations

import subprocess
from pathlib import Path


def main():
    project_root = Path(__file__).resolve().parent
    root_dist = project_root.parent.parent  # E:\MCU\MSPM0\Contest
    exe_name = "host_app"
    dist_dir = root_dist
    build_tmp = project_root / ".host_build_tmp"
    spec_dir = project_root / ".host_build_tmp"

    build_tmp.mkdir(exist_ok=True)
    cmd = [
        "pyinstaller",
        "--onefile",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_tmp / "work"),
        "--specpath",
        str(spec_dir),
        "--name",
        exe_name,
        "--add-data",
        f"{project_root / 'templates'};templates",
        "--add-data",
        f"{project_root / 'static'};static",
        "--hidden-import",
        "engineio.async_drivers.threading",
        "--hidden-import",
        "eventlet",
        "--hidden-import",
        "gevent",
        "--collect-all",
        "flask",
        "--collect-all",
        "flask_socketio",
        str(project_root / "app.py"),
    ]

    print("[BUILD] command:", " ".join(cmd))
    subprocess.run(cmd, check=True)

    exe_path = dist_dir / f"{exe_name}.exe"
    if exe_path.exists():
        print(f"[BUILD] ok: {exe_path}")
    else:
        raise SystemExit("build failed: exe not found")


if __name__ == "__main__":
    main()
