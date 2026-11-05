"""Convert each app's existing Windows artwork into Android launcher assets."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'accounting': ROOT / 'desktop/icon.png',
    'vendor': ROOT / 'source-app-updates/vendor/dist/icons/app.ico',
    'main': ROOT / 'source-app-updates/main/assets/icon.ico',
}


def prepare_icons(kind):
    artwork = Image.open(SOURCES[kind]).convert('RGBA')
    resources = ROOT / 'android-apps' / kind / 'android/app/src/main/res'
    for density, scale in [('mdpi', 1), ('hdpi', 1.5), ('xhdpi', 2), ('xxhdpi', 3), ('xxxhdpi', 4)]:
        folder = resources / ('mipmap-' + density)
        folder.mkdir(parents=True, exist_ok=True)
        icon = artwork.resize((round(48 * scale), round(48 * scale)), Image.Resampling.LANCZOS)
        for name in ['ic_launcher.png', 'ic_launcher_round.png']:
            icon.save(folder / name)
        # Android masks adaptive icons. Keep all original artwork inside the
        # central 66dp safe area of the 108dp foreground layer.
        size = round(108 * scale)
        foreground = Image.new('RGBA', (size, size))
        mark = artwork.resize((round(64 * scale), round(64 * scale)), Image.Resampling.LANCZOS)
        offset = (size - mark.width) // 2
        foreground.alpha_composite(mark, (offset, offset))
        foreground.save(folder / 'ic_launcher_foreground.png')
    print('Prepared ' + kind + ' Android icons from ' + SOURCES[kind].name)


if __name__ == '__main__':
    for app in ['accounting', 'vendor']:
        prepare_icons(app)
