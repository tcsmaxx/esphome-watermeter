"""Build the checked-in YAML against local sources with disposable dummy secrets.
Usage: python tests/build_check.py [--config-only]
Requires ESPHome 2026.9.1. Never reads or overwrites a user's secrets.yaml.
"""
import base64
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parent.parent
source = root / 'components'
yaml = (root / 'wasserzaehler.yaml').read_text()
yaml = yaml.replace('      type: git\n      url: https://github.com/tcsmaxx/esphome-watermeter\n      ref: main', f'      type: local\n      path: {source}')
with tempfile.TemporaryDirectory(prefix='meter-build-') as directory:
    config = Path(directory) / 'wasserzaehler.yaml'
    config.write_text(yaml)
    key = base64.b64encode(os.urandom(32)).decode()
    (Path(directory) / 'secrets.yaml').write_text(f'wifi_ssid: test\nwifi_password: testpassword\napi_encryption_key: {key}\nota_password: testpassword\nfallback_password: testpassword\nweb_username: admin\nweb_password: testpassword\n')
    result = subprocess.run([sys.executable, '-m', 'esphome', 'config' if '--config-only' in sys.argv else 'compile', str(config)])
    sys.exit(result.returncode)
