"""Build the offline application with bundled cards."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent

def main():
    expected = [f'{r}{s}.png' for s in 'SHDC'
                for r in ('2','3','4','5','6','7','8','9','10','J','Q','K','A')]
    expected += ['back.png', 'LICENSE-deckofcards.txt']
    missing = [name for name in expected if not (ROOT / 'assets' / name).is_file()]
    if missing:
        raise SystemExit('Missing bundled assets: ' + ', '.join(missing))
    result = subprocess.run(
        [sys.executable, '-m', 'PyInstaller', '--noconfirm', 'gui.spec'],
        cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    (ROOT / 'build_log.txt').write_text(result.stdout + result.stderr, encoding='utf-8')
    print('Build failed: see build_log.txt' if result.returncode else str(ROOT / 'dist' / 'ChinesePoker.exe'))
    return result.returncode

if __name__ == '__main__':
    sys.exit(main())
