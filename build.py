import subprocess
import sys

print("Starting PyInstaller build...")
try:
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed", "--add-data", "assets;assets", "gui.py"],
        capture_output=True,
        text=True
    )
    with open("build_log.txt", "w") as f:
        f.write("STDOUT:\n")
        f.write(result.stdout)
        f.write("\nSTDERR:\n")
        f.write(result.stderr)
    print("Build finished with code", result.returncode)
except Exception as e:
    print("Error:", e)
