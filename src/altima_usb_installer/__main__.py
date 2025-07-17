import sys
import os
import requests
import shutil
import subprocess
import traceback
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QComboBox,
    QMessageBox, QProgressBar, QHBoxLayout
)
from PySide6.QtGui import QPixmap, Qt
from PySide6.QtWebEngineWidgets import QWebEngineView

ALTIMA_LOGO_PATH = "altima-logo-100.png"
ALTIMA_ISO_LIST = "https://download.altimalinux.com/"
VENTOY_WIN_URL = "https://github.com/ventoy/Ventoy/releases/latest/download/ventoy-1.0.97-windows.zip"


class AltimaUSBInstaller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Altima USB Installer (Windows)")
        self.setMinimumWidth(600)

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
        self.web_view.setUrl("https://altimalinux.com/about")  # can be changed to slideshow

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

    def scan_usb_devices(self):
        try:
            if sys.platform.startswith("win"):
                try:
                    # ✅ Prefer PowerShell (Windows 8+)
                    output = subprocess.check_output(
                        ["powershell", "-Command",
                         "Get-Disk | Where-Object {$_.BusType -eq 'USB'} "
                         "| Select-Object -Property Number, FriendlyName, Size, BusType "
                         "| Format-Table -AutoSize"],
                        text=True
                    )
                except Exception:
                    # ✅ Fallback to WMIC if PowerShell fails
                    output = subprocess.check_output(
                        ["wmic", "diskdrive", "where", "InterfaceType='USB'",
                         "get", "Caption,DeviceID,Size"],
                        text=True
                    )

            elif sys.platform.startswith("linux"):
                output = subprocess.check_output(
                    ["lsblk", "-o", "NAME,SIZE,MODEL,TRAN"], text=True
                )
            else:
                output = "Unsupported platform."

            self.output_area.setPlainText(output)

        except Exception as e:
            error_msg = f"Error scanning USB devices:\n{traceback.format_exc()}"
            self.output_area.setPlainText(error_msg)


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

                r = requests.get(VENTOY_WIN_URL, stream=True)
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                self.progress.setValue(25)

                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(tmpdir)

                exe_path = next(Path(tmpdir).glob("ventoy*/Ventoy2Disk.exe"))
                result = subprocess.run([str(exe_path), "/I", device], capture_output=True)
                self.progress.setValue(80)
                if result.returncode == 0:
                    QMessageBox.information(self, "Success", "Ventoy installed successfully.")
                    self.progress.setValue(100)
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

            # Copy to Ventoy (assumes it's mounted automatically)
            shutil.copy(iso_path, f"{device}\\")  # copy to USB root
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
