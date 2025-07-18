import sys
import subprocess
import traceback
import requests
import zipfile
import os
import glob

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit,
    QHBoxLayout, QListWidget, QMessageBox
)
from PySide6.QtGui import QFont, QPixmap, QIcon
from PySide6.QtCore import Qt, QTimer

# --- App Constants ---
ALTIMA_LOGO_PATH = "src/altima_usb_installer/altima-logo-100.ico"
ALTIMA_ISO_LIST = "https://download.altimalinux.com/"
VENTOY_WIN_URL = "https://download.altimalinux.com/ventoy.zip"
VENTOY_DEST = "ventoy"

SLIDESHOW_IMAGES = [
    "src/altima_usb_installer/slides/slide1.png",
    "src/altima_usb_installer/slides/slide2.png",
    "src/altima_usb_installer/slides/slide3.png"
]


class AltimaUSBInstaller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Altima USB Installer")
        self.setGeometry(200, 200, 800, 500)
        self.setWindowIcon(QIcon(ALTIMA_LOGO_PATH))

        self.current_slide = 0
        self.selected_usb = None
        self.init_usb_screen()

    # =========================
    # SCREEN 1: USB Detection
    # =========================
    def init_usb_screen(self):
        self.layout = QHBoxLayout()
        self.left_layout = QVBoxLayout()

        title = QLabel("Insert USB stick, click Scan, then select a device:")
        title.setFont(QFont("Arial", 12, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        self.left_layout.addWidget(title)

        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.left_layout.addWidget(self.output_area)

        self.usb_list = QListWidget()
        self.left_layout.addWidget(self.usb_list)

        self.scan_button = QPushButton("Scan for USB Devices")
        self.scan_button.clicked.connect(self.scan_usb_devices)
        self.left_layout.addWidget(self.scan_button)

        self.ok_button = QPushButton("Prepare Ventoy")
        self.ok_button.clicked.connect(self.download_and_prepare_ventoy)
        self.ok_button.setEnabled(False)
        self.left_layout.addWidget(self.ok_button)

        self.layout.addLayout(self.left_layout)

        # Right panel (Static slideshow)
        self.slide_label = QLabel()
        self.slide_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.slide_label)
        self.setLayout(self.layout)

        self.start_slideshow()

    def start_slideshow(self):
        if SLIDESHOW_IMAGES:
            self.update_slide()
            self.timer = QTimer()
            self.timer.timeout.connect(self.next_slide)
            self.timer.start(5000)

    def update_slide(self):
        pixmap = QPixmap(SLIDESHOW_IMAGES[self.current_slide])
        self.slide_label.setPixmap(pixmap.scaled(380, 380, Qt.KeepAspectRatio))

    def next_slide(self):
        self.current_slide = (self.current_slide + 1) % len(SLIDESHOW_IMAGES)
        self.update_slide()

    def scan_usb_devices(self):
        self.output_area.setPlainText("Scanning for USB devices... please wait.")
        QApplication.processEvents()
        self.usb_list.clear()

        try:
            output = ""
            if sys.platform.startswith("win"):
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 0
                try:
                    output = subprocess.check_output(
                        [
                            "powershell",
                            "-NoLogo", "-NoProfile",
                            "-Command",
                            "Get-Disk | Where-Object {$_.BusType -eq 'USB'} "
                            "| Select-Object -Property Number, FriendlyName, Size, BusType "
                            "| Format-Table -AutoSize"
                        ],
                        text=True,
                        startupinfo=si
                    )
                except Exception:
                    output = subprocess.check_output(
                        [
                            "wmic", "diskdrive", "where", "InterfaceType='USB'",
                            "get", "Caption,DeviceID,Size"
                        ],
                        text=True,
                        startupinfo=si
                    )
            elif sys.platform.startswith("linux"):
                output = subprocess.check_output(
                    ["lsblk", "-o", "NAME,SIZE,MODEL,TRAN"], text=True
                )
            else:
                output = "Unsupported platform."

            self.output_area.setPlainText(output.strip())

            # ✅ Populate USB list
            lines = output.splitlines()
            for line in lines:
                if "USB" in line or "usb" in line.lower():
                    self.usb_list.addItem(line.strip())

            if self.usb_list.count() > 0:
                self.ok_button.setEnabled(True)
        except Exception:
            self.output_area.setPlainText(f"Error scanning USB devices:\n{traceback.format_exc()}")

    # =========================
    # SCREEN 2: Ventoy Download & Install
    # =========================
    def download_and_prepare_ventoy(self):
        if not self.usb_list.currentItem():
            QMessageBox.warning(self, "No USB Selected", "Please select a USB device first.")
            return

        self.selected_usb = self.usb_list.currentItem().text()
        self.output_area.setPlainText(f"Selected: {self.selected_usb}\nDownloading Ventoy...")
        QApplication.processEvents()

        try:
            os.makedirs(VENTOY_DEST, exist_ok=True)
            ventoy_zip_path = os.path.join(VENTOY_DEST, "ventoy.zip")

            with requests.get(VENTOY_WIN_URL, stream=True) as r:
                r.raise_for_status()
                total = int(r.headers.get('content-length', 0))
                downloaded = 0
                with open(ventoy_zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                percent = (downloaded / total) * 100
                                self.output_area.setPlainText(f"Downloading Ventoy... {percent:.2f}%")
                                QApplication.processEvents()

            with zipfile.ZipFile(ventoy_zip_path, "r") as zip_ref:
                zip_ref.extractall(VENTOY_DEST)

            self.output_area.setPlainText("✅ Ventoy downloaded. Running Ventoy2Disk...")
            QApplication.processEvents()

            # ✅ Find Ventoy2Disk.exe dynamically
            ventoy_folders = glob.glob(os.path.join(VENTOY_DEST, "ventoy-*"))
            if ventoy_folders:
                ventoy_exe = os.path.join(ventoy_folders[0], "Ventoy2Disk.exe")
                if os.path.exists(ventoy_exe):
                    subprocess.run([ventoy_exe], check=True)
                    self.goto_iso_screen()
                else:
                    self.output_area.setPlainText("❌ Ventoy2Disk.exe not found after extraction.")
            else:
                self.output_area.setPlainText("❌ Ventoy folder not found after extraction.")
        except Exception:
            self.output_area.setPlainText(f"Error preparing Ventoy:\n{traceback.format_exc()}")

    # =========================
    # SCREEN 3: ISO Download
    # =========================
    def goto_iso_screen(self):
        for i in reversed(range(self.left_layout.count())):
            widget = self.left_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        title = QLabel(f"Ventoy installed on: {self.selected_usb}\nDownload Altima Linux ISO")
        title.setFont(QFont("Arial", 12, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        self.left_layout.addWidget(title)

        iso_url_label = QLabel(f"Available ISOs: {ALTIMA_ISO_LIST}")
        iso_url_label.setAlignment(Qt.AlignCenter)
        self.left_layout.addWidget(iso_url_label)

        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.left_layout.addWidget(self.output_area)

        self.download_iso_button = QPushButton("Download ISO")
        self.download_iso_button.clicked.connect(self.download_iso)
        self.left_layout.addWidget(self.download_iso_button)

    def download_iso(self):
        self.output_area.setPlainText("Downloading ISO feature not implemented yet.")
        # Placeholder: will implement ISO selection & copy in next step


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(ALTIMA_LOGO_PATH))
    window = AltimaUSBInstaller()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with open("altima-error.log", "w") as f:
            traceback.print_exc(file=f)
        raise
