"""Render the home-screen icons (PNG) from public/favicon.svg.

iOS ignores SVG touch icons and draws a letter instead, so the app ships PNGs:
apple-touch-icon.png (180), icon-192.png, icon-512.png. They are the favicon's drawing on an
opaque tile (iOS fills transparency with black and rounds the corners itself), shrunk so the
mark stays inside the safe zone of an Android round mask. Re-run after changing favicon.svg or
TILE:  python frontend/scripts/make_icons.py   (needs Edge or Chrome, and Pillow)
"""
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

from PIL import Image

PUBLIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'public')
TILE = '#0C0D0F'   # icon background (owner's pick still open: the A-J options)
MARK_SCALE = 0.78  # mark size on the tile; under ~0.8 survives a round mask
RENDER = 1024
SIZES = {'apple-touch-icon.png': 180, 'icon-192.png': 192, 'icon-512.png': 512}

BROWSERS = [
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    'msedge', 'google-chrome', 'chromium', 'chromium-browser', 'chrome',
]


def browser():
    for b in BROWSERS:
        found = b if os.path.isfile(b) else shutil.which(b)
        if found:
            return found
    raise SystemExit('No Edge/Chrome found for the headless render')


def tile_svg():
    with open(os.path.join(PUBLIC, 'favicon.svg'), encoding='utf-8') as f:
        svg = f.read()
    inner = re.search(r'<svg[^>]*>(.*)</svg>', svg, re.S).group(1)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="100%" height="100%">'
            f'<rect width="64" height="64" fill="{TILE}"/>'
            f'<g transform="translate(32 32) scale({MARK_SCALE}) translate(-32 -33)">{inner}</g></svg>')


def main():
    exe = browser()
    with tempfile.TemporaryDirectory() as tmp:
        page = os.path.join(tmp, 'icon.html')
        with open(page, 'w', encoding='utf-8') as f:
            f.write('<!doctype html><html><body style="margin:0;overflow:hidden;background:'
                    f'{TILE}"><div style="width:100vw;height:100vh">{tile_svg()}</div></body></html>')
        # One big render, then downscale: headless windows have a minimum width, so a 180px
        # window screenshots blank.
        big = os.path.join(tmp, 'icon.png')
        subprocess.run([exe, '--headless=new', '--disable-gpu', '--hide-scrollbars',
                        f'--user-data-dir={os.path.join(tmp, "profile")}',
                        f'--window-size={RENDER},{RENDER}', f'--screenshot={big}',
                        pathlib.Path(page).as_uri()],
                       check=True, capture_output=True, timeout=60)
        with Image.open(big) as im:
            im = im.convert('RGB')
            for name, size in SIZES.items():
                im.resize((size, size), Image.LANCZOS).save(os.path.join(PUBLIC, name), optimize=True)
                print(f'{name}: {size}x{size}')

if __name__ == '__main__':
    main()
