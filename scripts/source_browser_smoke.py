"""Render the real source apps and APK assets, with fresh, offline browser profiles.

Requires Playwright and Chromium. Never signs in or reads existing company data.
"""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import shutil
import tempfile
from threading import Thread
import zipfile

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def check_login(browser, kind, directory, label):
    server = ThreadingHTTPServer(
        ('127.0.0.1', 0), partial(QuietHandler, directory=str(directory)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}/'
    try:
        for width, height in [(1280, 900), (390, 844)]:
            with browser.new_context(viewport={'width': width, 'height': height}) as context:
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(error.stack))
                # Only packaged files are accessible: no Firebase or other live requests.
                page.route('**/*', lambda route: route.continue_()
                           if route.request.url.startswith(base) else route.abort())
                page.goto(base)
                button = page.get_by_role('button', name=re.compile(
                    r'^\s*Login\s*$' if kind == 'main' else r'^\s*Sign in\s*$', re.I))
                button.wait_for(state='visible', timeout=15000)
                # Initial effects update state after mount; the regression crashed
                # during that transition, even though bundle syntax was valid.
                page.wait_for_timeout(1000)
                assert not errors, f'{label} {width}px: {errors}'
                assert button.is_visible() and button.is_enabled(), label
                password = page.locator('input[type=password]')
                assert password.count() >= 1 and password.first.is_visible(), label
                assert page.locator('#root').inner_text().strip(), label
                print(f'PASS {label} {width}px: visible login and password, no runtime errors')
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk-dir', type=Path,
                        help='Also render the actual main/vendor APK web assets')
    args = parser.parse_args()
    with sync_playwright() as playwright:
        options = {'headless': True, 'args': ['--no-sandbox']}
        executable = shutil.which('chromium') or shutil.which('chromium-browser')
        if executable:
            options['executable_path'] = executable
        with playwright.chromium.launch(**options) as browser:
            for kind, web in [('main', 'www'), ('vendor', 'dist')]:
                source = ROOT / 'source-app-updates' / kind / web
                check_login(browser, kind, source, f'{kind} desktop assets')
                if args.apk_dir:
                    prefix = 'Backwoods-Brew-Connected-' if kind == 'main' else 'Backwoods-Vendor-Connected-'
                    files = list(args.apk_dir.glob(prefix + '*-test.apk'))
                    assert len(files) == 1, f'Expected one current {kind} APK, found {files}'
                    with tempfile.TemporaryDirectory() as folder, zipfile.ZipFile(files[0]) as archive:
                        destination = Path(folder)
                        for name in archive.namelist():
                            if not name.startswith('assets/public/') or name.endswith('/'):
                                continue
                            relative = Path(name.removeprefix('assets/public/'))
                            target = (destination / relative).resolve()
                            assert target.is_relative_to(destination.resolve()), name
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_bytes(archive.read(name))
                        assert (destination / 'index.html').exists(), files[0]
                        for original in source.rglob('*'):
                            if original.is_file():
                                relative = original.relative_to(source)
                                assert (destination / relative).read_bytes() == original.read_bytes(), relative
                        check_login(browser, kind, destination, f'{kind} packaged APK assets')


if __name__ == '__main__':
    main()
