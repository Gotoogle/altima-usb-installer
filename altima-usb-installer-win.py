#!/usr/bin/env python3
# Altima USB Installer v2.2.1

import sys
import subprocess
import requests
import zipfile
import os
import shutil
import threading
import traceback
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QTextEdit, QVBoxLayout,
    QHBoxLayout, QSizePolicy, QComboBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QPixmap, QIcon

VENTOY_URL = "https://downloads.altimalinux.com/ventoy.zip"
ISO_LIST_URL = "https://downloads.altimalinux.com/altima-iso-list.json"
ICON_PATH = "altima-logo-100.png"

class AltimaInstaller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Altima USB Installer")
        self.setFixedSize(640, 400)
        self.setWindowIcon(QIcon(ICON_PATH))

        self.layout = QHBoxLayout()
        self.left_panel = QVBoxLayout()
        self.right_panel = QVBoxLayout()

        self.logo_label = QLabel()
        self.logo_label.setPixmap(QPixmap(ICON_PATH).scaled(100, 100, Qt.KeepAspectRatio))
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.right_panel.addWidget(self.logo_label)

        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        self.text_display.setFont(QFont("Arial", 10))
        self.right_panel.addWidget(self.text_display)

        self.messages = [
            "Altima Linux is designed for simplicity and independence.",
            "Install Altima and reclaim your digital freedom.",
            "Powered by Debian. Built for clarity."
        ]
        self.message_index = 0
        self.update_text()
        QTimer.singleShot(1000, self.rotate_message)

        self.usb_combo = QComboBox()
        self.left_panel.addWidget(QLabel("Select USB Device:"))
        self.left_panel.addWidget(self.usb_combo)

        self.scan_btn = QPushButton("Scan for USB Devices")
        self.scan_btn.clicked.connect(self.scan_usb)
        self.left_panel.addWidget(self.scan_btn)

        self.download_btn = QPushButton("Download and Install Ventoy")
        self.download_btn.clicked.connect(self.download_and_install_ventoy)
        self.left_panel.addWidget(self.download_btn)

        self.iso_btn = QPushButton("Download ISO and Copy to USB")
        self.iso_btn.clicked.connect(self.download_and_copy_iso)
        self.left_panel.addWidget(self.iso_btn)

        self.left_panel.addStretch()
        self.layout.addLayout(self.left_panel, 1)
        self.layout.addLayout(self.right_panel, 2)
        self.setLayout(self.layout)

    def update_text(self):
        self.text_display.setPlainText(self.messages[self.message_index])

    def rotate_message(self):
        self.message_index = (self.message_index + 1) % len(self.messages)
        self.update_text()
        QTimer.singleShot(5000, self.rotate_message)

    def scan_usb(self):
        self.usb_combo.clear()
        try:
            output = subprocess.check_output(
                ["powershell", "-Command",
                 "Get-CimInstance Win32_DiskDrive | Where-Object {$_.InterfaceType -eq 'USB'} | Select-Object -ExpandProperty DeviceID"],
                text=True, stderr=subprocess.DEVNULL
            )
            devices = [line.strip() for line in output.splitlines() if line.strip()]
            if devices:
                self.usb_combo.addItems(devices)
                self.text_display.setPlainText("USB devices detected.")
            else:
                self.text_display.setPlainText("No USB devices found.")
        except Exception as e:
            self.text_display.setPlainText(f"Error: {e}")

    def download_and_install_ventoy(self):
        self.text_display.setPlainText("Downloading Ventoy...")
        threading.Thread(target=self._download_and_extract_zip, args=(VENTOY_URL, "ventoy"), daemon=True).start()

    def _download_and_extract_zip(self, url, dest):
        try:
            os.makedirs(dest, exist_ok=True)
            zip_path = os.path.join(dest, "ventoy.zip")
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(dest)
            exe_path = self._find_ventoy_exe(dest)
            if exe_path:
                subprocess.run([exe_path], shell=True)
            self.text_display.setPlainText("Ventoy installed.")
        except Exception:
            self.text_display.setPlainText(traceback.format_exc())

    def _find_ventoy_exe(self, folder):
        for root, _, files in os.walk(folder):
            for f in files:
                if f.lower() == "ventoy2disk.exe":
                    return os.path.join(root, f)
        return None

    def download_and_copy_iso(self):
        self.text_display.setPlainText("Fetching ISO list...")
        try:
            response = requests.get(ISO_LIST_URL)
            response.raise_for_status()
            data = response.json()
            iso_url = data["isos"][0]["url"]  # pick first one
            self.text_display.setPlainText("Downloading ISO...")
            iso_path = os.path.join("iso", os.path.basename(iso_url))
            os.makedirs("iso", exist_ok=True)
            with requests.get(iso_url, stream=True) as r:
                r.raise_for_status()
                with open(iso_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            target = self.usb_combo.currentText()
            if target:
                subprocess.run(["xcopy", iso_path, target], shell=True)
                self.text_display.setPlainText("ISO copied to USB.")
            else:
                self.text_display.setPlainText("No USB selected.")
        except Exception:
            self.text_display.setPlainText(traceback.format_exc())

def main():
    app = QApplication(sys.argv)
    window = AltimaInstaller()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
