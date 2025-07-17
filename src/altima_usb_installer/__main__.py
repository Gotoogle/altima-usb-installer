import sys
import os
import requests
import shutil
import subprocess
import traceback
import zipfile
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QComboBox,
    QMessageBox, QProgressBar
)
from PySide6.QtGui import QPixmap, Qt
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QTimer

ALTIMA_LOGO_PATH = "altima-logo-100.png"
ALTIMA_ISO_LIST = "https://download.altimalinux.com/"
VENTOY_WIN_URL = "https://github.com/ventoy/Ventoy/releases/latest/download/ventoy-1.0.97-windows.zip"

INFO_PAGES = [
    "https://altimalinux.com/about",
    "https://altimalinux.com/features",
    "https://altimalinux.com/screenshots"
]


class AltimaUSBInstaller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Altima USB Installer (Windows)")
        self.setMinimumWidth(640)

        # --- Widgets ---
        self.logo = QLabel()
        self.logo.setAlignment(Qt.AlignCenter)
        self.logo.setPixmap(QPixmap(ALTIMA_LOGO_PATH).scaledToHeight(100))

        self.info_label = QLabel("Insert a USB stick >8GB and select it below.")
        self.device_select = QComboBox()
        self.rescan_button = QPushButton("Rescan USB Devices")
        self.rescan_button.clicked.connect(self.scan_usb_devices)

        self.ventoy_button = QPushButton("Install Ventoy on USB")
        self.ventoy_button.clicked.connect(self.install_ventoy)

        self.iso_select = QComboBox()
        self.load_iso_list()

        self.download_button = QPushButton("Download & Copy ISO")
        self.download_button.clicked.connect(self.download_and_copy_iso)

        self.progress = QProgressBar()

        # --- Web Info Panel ---
        self.web_view = QWebEngineView()
        self.page_index = 0
        self.web_view.setUrl(INFO_PAGES[self.page_index])
        self.timer = QTimer()
        self.timer.timeout.connect(self.rotate_pages)
        self.timer.start(10000)  # rotate every 10 seconds

        # --- Layout ---
        layout = QVBoxLayout()
        layout.addWidget(self.logo)
        layout.addWidget(self.info_label)
        layout.addWidget(self.device_select)
        layout.addWidget(self.rescan_button)
        layout.addWidget(self.ventoy_button)
        layout.addWidget(QLabel("Select ISO:"))
        layout.addWidget(self.iso_select)
        layout.addWidget(self.download_button)
        layout.addWidget(self.progress)
        layout.addWidget(self.web_view)
        self.setLayout(layout)

        # Initial scan
        self.scan_usb_devices()

    def rotate_pages(self):
        """Rotate info pages in web panel"""
        self.page_index = (self.page_index + 1) % len(INFO_PAGES)
        self.web_view.setUrl(INFO_PAGES[self.page_index])

    def scan_usb_devices(self):
        """Scan removable USB sticks (Windows only)"""
        self.device_select.clear()
        try:
            output = subprocess.check_output(
                ["wmic", "logicaldisk", "get", "DeviceID,VolumeName,Size,DriveType"],
                text=True
            )
            for line in output.splitlines()[1:]:
                if "2" in line:  # DriveType 2 = Removable Disk
                    parts = [p.strip() for p in line.split() if p.strip()]
                    if len(parts) >= 3:
                        device, label, size = parts[0], parts[1], parts[2]
                        try:
                            size_gb = int(size) / (1024**3)
                            if size_gb > 8:
                                self.device_select.addItem(f"{device} ({label}) {size_gb:.1f} GB")
                        except ValueError:
                            continue
            if self.device_select.count() == 0:
                QMessageBox.warning(self, "No USB", "No USB sticks >8GB found. Insert one and rescan.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"USB scan failed:\n{e}")

    def load_iso_list(self):
        """Load ISO list from Altima download server"""
        try:
            html = requests.get(ALTIMA_ISO_LIST).text
            import re
            isos = re.findall(r'href=\"([^"]+\.iso)\"', html)
            for iso in sorted(set(isos)):
                self.iso_select.addItem(iso)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load ISO list:\n{e}")

    def install_ventoy(self):
        """Download and install Ventoy on selected USB"""
        disk_entry = self.device_select.currentText()
        if not disk_entry:
            QMessageBox.warning(self, "No USB", "Please select a USB device.")
            return
        device = disk_entry.split()[0]

        confirm = QMessageBox.question(
            self, "Confirm",
            f"Ventoy will erase all data on {device}. Proceed?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            with TemporaryDirectory() as tmpdir:
                self.progress.setValue(5)
                zip_path = Path(tmpdir) / "ventoy.zip"

                # Download Ventoy zip
                r = requests.get(VENTOY_WIN_URL, stream=True)
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                self.progress.setValue(25)

                # Extract Ventoy
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(tmpdir)

                exe_path = next(Path(tmpdir).glob("ventoy*/Ventoy2Disk.exe"))
                result = subprocess.run([str(exe_path), "/I", device], capture_output=True)
                self.progress.setValue(80)
                if result.returncode == 0:
                    QMessageBox.information(self, "Success", "Ventoy installed successfully.")
                    self.progress.setValue(100)
                    # Wait for drive remount
                    time.sleep(5)
                    self.scan_usb_devices()
                else:
                    QMessageBox.critical(self, "Failed", result.stderr.decode())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Ventoy install failed:\n{e}")

    def download_and_copy_iso(self):
        """Download selected Altima ISO and copy to Ventoy partition"""
        iso_file = self.iso_select.currentText()
        if not iso_file:
            return
        device = self.device_select.currentText().split()[0]
        iso_url = ALTIMA_ISO_LIST + iso_file

        try:
            self.progress.setValue(0)
            iso_path = Path.home() / "Downloads" / iso_file

            # Download ISO
            r = requests.get(iso_url, stream=True)
            total = int(r.headers.get("content-length", 0))
            with open(iso_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    self.progress.setValue(int(f.tell() / total * 100 * 0.5))
            self.progress.setValue(50)

            # Copy to USB root
            shutil.copy(iso_path, f"{device}\\")
            self.progress.setValue(100)
            QMessageBox.information(self, "Done", f"{iso_file} copied to USB.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"ISO copy failed:\n{e}")


def main():
    app = QApplication(sys.argv)
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
