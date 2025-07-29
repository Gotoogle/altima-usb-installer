#!/usr/bin/env python3
# Altima USB Installer - Windows Version
# Version: 2.1.5

import sys
import os
import subprocess
import traceback
import requests
import zipfile
import shutil
import threading
import json

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QListWidget, QProgressBar, QCheckBox
)
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt, QTimer

APP_VERSION = "2.1.5"

ALTIMA_ISO_LIST_URL = "https://download.altimalinux.com/altima-iso-list.json"
VENTOY_ZIP_URL = "https://download.altimalinux.com/ventoy.zip"
VENTOY_DEST_DIR = "ventoy"
ICON_PATH = "altima-logo-100.ico"
LOGO_PATH = "altima-logo-100.png"

ROTATING_MESSAGES = [
    f"Altima USB Installer v{APP_VERSION}",
    "Turn any USB drive into a bootable Altima Linux installer.",
    "Powered by Ventoy and built for simplicity.",
]

class AltimaUSBInstaller(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"Altima USB Installer v{APP_VERSION}")
        self.setGeometry(100, 100, 900, 500)

        # Icon
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
            print(f"✔ Icon loaded: {ICON_PATH}")
        elif os.path.exists(LOGO_PATH):
            self.setWindowIcon(QIcon(LOGO_PATH))
            print(f"✔ Fallback icon loaded: {LOGO_PATH}")
        else:
            print("⚠ No icon file found.")

        # Layout
        self.main_layout = QHBoxLayout()
        self.left_layout = QVBoxLayout()
        self.right_layout = QVBoxLayout()
        self.setLayout(self.main_layout)
        self.main_layout.addLayout(self.left_layout, 1)
        self.main_layout.addLayout(self.right_layout, 2)

        # Logo
        if os.path.exists(LOGO_PATH):
            logo_label = QLabel()
            logo_label.setPixmap(QPixmap(LOGO_PATH).scaledToWidth(120))
            logo_label.setAlignment(Qt.AlignCenter)
            self.right_layout.addWidget(logo_label)

        # Rotating text
        self.message_label = QLabel(ROTATING_MESSAGES[0])
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        self.right_layout.addWidget(self.message_label)

        self.msg_index = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.rotate_message)
        self.timer.start(5000)

        # USB output
        self.usb_output = QTextEdit()
        self.usb_output.setReadOnly(True)
        self.usb_output.setFixedHeight(120)
        self.left_layout.addWidget(self.usb_output)

        self.usb_list = QListWidget()
        self.left_layout.addWidget(self.usb_list)

        # Buttons
        self.scan_button = QPushButton("Scan for USB Devices")
        self.scan_button.clicked.connect(self.scan_usb_devices)
        self.left_layout.addWidget(self.scan_button)

        self.ventoy_button = QPushButton("Download and Install Ventoy")
        self.ventoy_button.clicked.connect(self.download_and_prepare_ventoy)
        self.left_layout.addWidget(self.ventoy_button)

        self.iso_button = QPushButton("Download Altima ISO")
        self.iso_button.setEnabled(False)
        self.iso_button.clicked.connect(self.download_iso)
        self.left_layout.addWidget(self.iso_button)

        # Progress bar
        self.progress = QProgressBar()
        self.left_layout.addWidget(self.progress)

        # Eject
        self.eject_checkbox = QCheckBox("Eject USB after ISO copy")
        self.left_layout.addWidget(self.eject_checkbox)

    def rotate_message(self):
        self.msg_index = (self.msg_index + 1) % len(ROTATING_MESSAGES)
        self.message_label.setText(ROTATING_MESSAGES[self.msg_index])

    def scan_usb_devices(self):
        self.usb_output.setPlainText("Scanning for USB devices...")
        self.usb_list.clear()

        def worker():
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 0
                output = subprocess.check_output([
                    "powershell", "-NoProfile", "-Command",
                    "(Get-Disk | Where-Object {$_.BusType -eq 'USB'}) | ForEach-Object {\"$($_.Number) | $($_.FriendlyName) | $([math]::Round($_.Size/1GB))GB\"}"
                ], startupinfo=si, text=True)
                lines = [l.strip() for l in output.splitlines() if l.strip()]
                if lines:
                    self.usb_output.setPlainText("\n".join(lines))
                    self.usb_list.addItems(lines)
                    self.ventoy_button.setEnabled(True)
                else:
                    self.usb_output.setPlainText("⚠ No USB devices detected.")
            except Exception as e:
                self.usb_output.setPlainText("❌ USB scan failed.\n" + traceback.format_exc())

        threading.Thread(target=worker, daemon=True).start()

    def download_and_prepare_ventoy(self):
        self.progress.setValue(0)
        self.usb_output.setPlainText("⬇ Downloading Ventoy...")

        def worker():
            try:
                os.makedirs(VENTOY_DEST_DIR, exist_ok=True)
                zip_path = os.path.join(VENTOY_DEST_DIR, "ventoy.zip")
                with requests.get(VENTOY_ZIP_URL, stream=True) as r:
                    r.raise_for_status()
                    total = int(r.headers.get('content-length', 0))
                    with open(zip_path, "wb") as f:
                        downloaded = 0
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total:
                                percent = int((downloaded / total) * 100)
                                self.progress.setValue(percent)
                self.usb_output.setPlainText("✔ Ventoy downloaded. Extracting...")
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(VENTOY_DEST_DIR)
                exe = self.find_ventoy_exe()
                if exe:
                    self.usb_output.setPlainText(f"Launching: {exe}")
                    subprocess.run([exe], check=True)
                    self.iso_button.setEnabled(True)
                else:
                    self.usb_output.setPlainText("❌ Could not find Ventoy2Disk.exe.")
            except Exception as e:
                self.usb_output.setPlainText("❌ Error preparing Ventoy:\n" + traceback.format_exc())

        threading.Thread(target=worker, daemon=True).start()

    def find_ventoy_exe(self):
        for root, _, files in os.walk(VENTOY_DEST_DIR):
            for f in files:
                if f.lower() == "ventoy2disk.exe":
                    return os.path.join(root, f)
        return None

    def download_iso(self):
        self.usb_output.setPlainText("⬇ Fetching Altima ISO list...")

        def worker():
            try:
                r = requests.get(ALTIMA_ISO_LIST_URL)
                r.raise_for_status()
                isos = r.json()
                if not isos:
                    self.usb_output.setPlainText("⚠ No ISOs found.")
                    return
                iso_url = isos[0]["url"]
                iso_name = iso_url.split("/")[-1]
                with requests.get(iso_url, stream=True) as r:
                    r.raise_for_status()
                    total = int(r.headers.get('content-length', 0))
                    with open(iso_name, "wb") as f:
                        downloaded = 0
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total:
                                percent = int((downloaded / total) * 100)
                                self.progress.setValue(percent)
                self.usb_output.setPlainText(f"✔ Download complete: {iso_name}")
                if self.eject_checkbox.isChecked():
                    self.usb_output.append("🔌 Please eject USB manually.")
            except Exception as e:
                self.usb_output.setPlainText("❌ ISO download failed:\n" + traceback.format_exc())

        threading.Thread(target=worker, daemon=True).start()


def main():
    app = QApplication(sys.argv)
    win = AltimaUSBInstaller()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
