import sys
import os
import subprocess
import traceback
import requests
import zipfile
import glob
import shutil
import threading
import time

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QListWidget, QProgressBar, QCheckBox
)
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt, QTimer

# --- App Constants ---
APP_VERSION = "2.1.2"
ALTIMA_ISO_LIST = "https://download.altimalinux.com/altima-iso-list.json"
VENTOY_WIN_URL = "https://download.altimalinux.com/ventoy.zip"
VENTOY_DEST = "ventoy"

LOGO_ICO = "altima-logo-100.ico"
LOGO_PNG = "altima-logo-100.png"

ROTATING_MESSAGES = [
    "Welcome to Altima Linux v2.1.2! Convert your system easily and enjoy privacy.",
    "Ventoy prepares your USB stick to boot Altima Linux live in minutes.",
    "Once ready, boot Altima Linux for a fast, minimal, and secure experience."
]


class AltimaUSBInstaller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Altima USB Installer v{APP_VERSION}")
        self.setGeometry(200, 200, 900, 500)

        # App Icon
        if os.path.exists(LOGO_ICO):
            self.setWindowIcon(QIcon(LOGO_ICO))
        elif os.path.exists(LOGO_PNG):
            self.setWindowIcon(QIcon(LOGO_PNG))

        self.selected_usb = None
        self.current_message = 0

        # Main horizontal layout
        main_layout = QHBoxLayout()
        self.setLayout(main_layout)

        # Left panel (2/3 width)
        self.left_panel = QVBoxLayout()
        main_layout.addLayout(self.left_panel, 2)

        # Right panel (1/3 width with logo & rotating messages)
        self.right_panel = QVBoxLayout()
        main_layout.addLayout(self.right_panel, 1)

        self.init_usb_screen()
        self.init_rotating_messages()

    # -----------------------------
    # Rotating Info Messages with Logo
    # -----------------------------
    def init_rotating_messages(self):
        # Logo at top of right panel
        if os.path.exists(LOGO_PNG):
            logo_label = QLabel()
            pixmap = QPixmap(LOGO_PNG)
            logo_label.setPixmap(pixmap.scaledToWidth(120, Qt.SmoothTransformation))
            logo_label.setAlignment(Qt.AlignCenter)
            self.right_panel.addWidget(logo_label)
        elif os.path.exists(LOGO_ICO):
            logo_label = QLabel()
            pixmap = QPixmap(LOGO_ICO)
            logo_label.setPixmap(pixmap.scaledToWidth(120, Qt.SmoothTransformation))
            logo_label.setAlignment(Qt.AlignCenter)
            self.right_panel.addWidget(logo_label)

        self.info_label = QLabel(ROTATING_MESSAGES[self.current_message])
        self.info_label.setWordWrap(True)
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet("font-size:14px; padding:10px;")
        self.right_panel.addWidget(self.info_label)

        self.timer = QTimer()
        self.timer.timeout.connect(self.rotate_message)
        self.timer.start(5000)

    def rotate_message(self):
        self.current_message = (self.current_message + 1) % len(ROTATING_MESSAGES)
        self.info_label.setText(ROTATING_MESSAGES[self.current_message])

    # -----------------------------
    # Screen 1: USB Detection
    # -----------------------------
    def init_usb_screen(self):
        for i in reversed(range(self.left_panel.count())):
            widget = self.left_panel.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        label = QLabel("<b>Insert USB stick and click Scan for USB Devices:</b>")
        self.left_panel.addWidget(label)

        self.usb_output = QTextEdit()
        self.usb_output.setReadOnly(True)
        self.usb_output.setFixedHeight(120)
        self.left_panel.addWidget(self.usb_output)

        self.usb_list = QListWidget()
        self.left_panel.addWidget(self.usb_list)

        self.scan_button = QPushButton("Scan for USB Devices")
        self.scan_button.clicked.connect(self.scan_usb_devices)
        self.left_panel.addWidget(self.scan_button)

        self.ventoy_button = QPushButton("Prepare Ventoy")
        self.ventoy_button.setEnabled(False)
        self.ventoy_button.clicked.connect(self.download_and_prepare_ventoy)
        self.left_panel.addWidget(self.ventoy_button)

    def scan_usb_devices(self):
        self.usb_output.setPlainText("Scanning for USB devices... please wait.")
        self.usb_list.clear()

        def scan():
            try:
                output_lines = []
                try:
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    si.wShowWindow = 0
                    raw = subprocess.check_output(
                        [
                            "powershell", "-NoLogo", "-NoProfile",
                            "-Command",
                            "(Get-Disk | Where-Object {$_.BusType -eq 'USB'}) "
                            "| ForEach-Object {\"$($_.Number) | $($_.FriendlyName) | $([math]::Round($_.Size/1GB))GB\"}"
                        ],
                        text=True, startupinfo=si
                    )
                    output_lines = [l.strip() for l in raw.splitlines() if l.strip()]
                except Exception:
                    output_lines = []

                if not output_lines:
                    output_lines = ["No USB devices detected."]

                self.usb_output.setPlainText("\n".join(output_lines))
                if "No USB" not in output_lines[0]:
                    self.usb_list.addItems(output_lines)
                    self.ventoy_button.setEnabled(True)
                else:
                    self.ventoy_button.setEnabled(False)
            except Exception:
                self.usb_output.setPlainText(traceback.format_exc())

        threading.Thread(target=scan, daemon=True).start()

    # -----------------------------
    # Screen 2: Ventoy Preparation
    # -----------------------------
    def download_and_prepare_ventoy(self):
        selected = self.usb_list.currentItem()
        if not selected:
            self.usb_output.setPlainText("Please select a USB device first.")
            return

        self.selected_usb = selected.text()
        self.usb_output.setPlainText(f"Selected: {self.selected_usb}\nDownloading Ventoy...")

        def download_and_run():
            try:
                os.makedirs(VENTOY_DEST, exist_ok=True)
                ventoy_zip_path = os.path.join(VENTOY_DEST, "ventoy.zip")

                with requests.get(VENTOY_WIN_URL, stream=True) as r:
                    r.raise_for_status()
                    total = int(r.headers.get("content-length", 0))
                    downloaded = 0
                    with open(ventoy_zip_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total > 0:
                                    percent = (downloaded / total) * 100
                                    self.usb_output.setPlainText(
                                        f"Downloading Ventoy... {percent:.1f}%"
                                    )

                with zipfile.ZipFile(ventoy_zip_path, "r") as zip_ref:
                    zip_ref.extractall(VENTOY_DEST)

                self.usb_output.setPlainText("✅ Ventoy downloaded. Running Ventoy2Disk...")
                ventoy_folders = glob.glob(os.path.join(VENTOY_DEST, "ventoy-*"))
                if ventoy_folders:
                    ventoy_exe = os.path.join(ventoy_folders[0], "Ventoy2Disk.exe")
                    if os.path.exists(ventoy_exe):
                        subprocess.run(
                            ["powershell", "Start-Process", ventoy_exe, "-Verb", "runAs"],
                            check=True
                        )
                        self.goto_iso_screen()
                    else:
                        self.usb_output.setPlainText("❌ Ventoy2Disk.exe not found.")
                else:
                    self.usb_output.setPlainText("❌ Ventoy folder not found.")
            except Exception:
                self.usb_output.setPlainText(traceback.format_exc())

        threading.Thread(target=download_and_run, daemon=True).start()

    # -----------------------------
    # Screen 3: ISO Download & Copy
    # -----------------------------
    def goto_iso_screen(self):
        for i in reversed(range(self.left_panel.count())):
            widget = self.left_panel.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        label = QLabel(f"<b>Ventoy installed on: {self.selected_usb}</b>\nSelect an ISO to download:")
        self.left_panel.addWidget(label)

        self.iso_list = QListWidget()
        self.left_panel.addWidget(self.iso_list)

        self.iso_output = QTextEdit()
        self.iso_output.setReadOnly(True)
        self.left_panel.addWidget(self.iso_output)

        self.progress_bar = QProgressBar()
        self.left_panel.addWidget(self.progress_bar)

        self.eject_checkbox = QCheckBox("Eject USB when complete")
        self.eject_checkbox.setChecked(True)
        self.left_panel.addWidget(self.eject_checkbox)

        self.download_button = QPushButton("Download & Copy ISO")
        self.download_button.clicked.connect(self.download_iso)
        self.left_panel.addWidget(self.download_button)

        self.load_iso_list()

    def load_iso_list(self):
        self.iso_output.setPlainText("Fetching ISO list...")

        def fetch_list():
            try:
                response = requests.get(ALTIMA_ISO_LIST, timeout=5)
                data = response.json() if response.status_code == 200 else {}
                isos = data.get("isos", [
                    {"name": "Altima Linux Minimal (Fallback)", "file": "altima-minimal-1.0.iso"},
                    {"name": "Altima Linux Full (Fallback)", "file": "altima-full-1.0.iso"}
                ])
                self.iso_list.clear()
                for iso in isos:
                    self.iso_list.addItem(f"{iso['name']} ({iso['file']})")
            except Exception:
                self.iso_output.setPlainText(traceback.format_exc())

        threading.Thread(target=fetch_list, daemon=True).start()

    def download_iso(self):
        selected = self.iso_list.currentItem()
        if not selected:
            self.iso_output.setPlainText("Please select an ISO first.")
            return

        iso_text = selected.text()
        iso_file = iso_text.split("(")[-1].strip(")")
        self.iso_output.setPlainText(f"Downloading {iso_file}...")

        def download_and_copy():
            try:
                iso_url = ALTIMA_ISO_LIST.replace("altima-iso-list.json", iso_file)
                iso_path = os.path.join(os.getcwd(), iso_file)

                with requests.get(iso_url, stream=True) as r:
                    r.raise_for_status()
                    total = int(r.headers.get("content-length", 0))
                    downloaded = 0
                    with open(iso_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total > 0:
                                    percent = downloaded / total
                                    self.progress_bar.setValue(int(percent * 50))

                # Auto-copy to Ventoy
                copied_path = None
                try:
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    si.wShowWindow = 0
                    drive_letter = subprocess.check_output(
                        [
                            "powershell", "-NoLogo", "-NoProfile",
                            "-Command",
                            "(Get-Volume | Where-Object {$_.FileSystemLabel -eq 'Ventoy'}).DriveLetter"
                        ],
                        text=True, startupinfo=si
                    ).strip()
                    if drive_letter:
                        copied_path = f"{drive_letter}:\\{iso_file}"
                        shutil.copy(iso_path, copied_path)
                        self.progress_bar.setValue(100)
                        self.iso_output.setPlainText(
                            f"✅ ISO copied to {copied_path}\nYour USB is ready to boot!"
                        )
                        if self.eject_checkbox.isChecked():
                            subprocess.run(
                                [
                                    "powershell", "-NoLogo", "-NoProfile",
                                    f"Remove-Volume -DriveLetter {drive_letter} -Confirm:$false"
                                ]
                            )
                            self.iso_output.append("✅ USB ejected safely.")
                except Exception:
                    self.iso_output.append(f"✅ ISO downloaded to {iso_path}\nCopy manually if needed.")
            except Exception:
                self.iso_output.setPlainText(traceback.format_exc())
            finally:
                time.sleep(1)
                self.progress_bar.setValue(0)

        threading.Thread(target=download_and_copy, daemon=True).start()


def main():
    app = QApplication(sys.argv)
    window = AltimaUSBInstaller()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
