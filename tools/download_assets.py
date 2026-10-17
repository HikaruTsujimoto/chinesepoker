"""Restore bundled images from a pinned upstream revision."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen

REVISION = 'fa7d8f08e1ba1f2304216374585e65a614e1fb8d'
BASE = f'https://raw.githubusercontent.com/crobertsbmw/deckofcards/{REVISION}'
ASSETS = Path(__file__).resolve().parents[1] / 'assets'

def download_cards():
    ASSETS.mkdir(exist_ok=True)
    files = [(f'{r}{s}.png', f'{"0" if r == "10" else r}{s}.png')
             for s in 'SHDC' for r in ('2','3','4','5','6','7','8','9','10','J','Q','K','A')]
    files.append(('back.png', 'back.png'))
    def download(entry):
        name, upstream = entry
        with urlopen(f'{BASE}/static/img/{upstream}', timeout=30) as response:
            data = response.read()
        if not data.startswith(bytes.fromhex('89504e470d0a1a0a')):
            raise ValueError(f'Invalid PNG: {name}')
        (ASSETS / name).write_bytes(data)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(download, files))
    with urlopen(f'{BASE}/LICENSE.txt', timeout=30) as response:
        (ASSETS / 'LICENSE-deckofcards.txt').write_bytes(response.read())
    print('Restored 52 cards, one back, and license.')

if __name__ == '__main__':
    download_cards()
