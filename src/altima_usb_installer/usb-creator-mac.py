import os
import sys
import requests
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QComboBox, QMessageBox, QProgressBar
)
from PySide6.QtGui import QPixmap, Qt

ALTIMA_LOGO_PATH = "altima-logo.png"
VENTOY_RELEASE = "https://github.com/ventoy/Ventoy/releases/latest/download/ventoy-1.0.97-macos.tar.gz"
ALTIMA_ISO_LIST = "https://download.altimalinux.com/"

class AltimaUSBFlasher(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Altima USB Installer")
        self.setMinimumWidth(420)

        self.label = QLabel("Insert a USB stick >8GB and select it below.")
        self.logo = QLabel()
        self.logo.setAlignment(Qt.AlignCenter)
        self.logo.setPixmap(QPixmap(ALTIMA_LOGO_PATH).scaledToHeight(100))

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

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.logo)
        layout.addWidget(self.label)
        layout.addWidget(self.device_select)
        layout.addWidget(self.rescan_button)
        layout.addWidget(self.ventoy_button)
        layout.addWidget(QLabel("Select ISO:"))
        layout.addWidget(self.iso_select)
        layout.addWidget(self.download_button)
        layout.addWidget(self.progress)

        self.setLayout(layout)
        self.scan_usb_devices()

    def scan_usb_devices(self):
        self.device_select.clear()
        output = subprocess.check_output(["diskutil", "list", "-plist"])
        from plistlib import loads
        devices = loads(output)["AllDisksAndPartitions"]
        for d in devices:
            size = d.get("Size", 0)
            identifier = d["DeviceIdentifier"]
            if size > 8 * 1024**3 and not identifier.startswith("disk0"):
                self.device_select.addItem(f"/dev/{identifier} ({size // 1024**3} GB)")

    def load_iso_list(self):
        try:
            html = requests.get(ALTIMA_ISO_LIST).text
            import re
            isos = re.findall(r'href="([^"]+\.iso)"', html)
            for iso in sorted(set(isos)):
                self.iso_select.addItem(iso)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load ISO list:\n{e}")

    def install_ventoy(self):
        disk_entry = self.device_select.currentText()
        if not disk_entry:
            QMessageBox.warning(self, "No USB", "Please select a USB device.")
            return
        device = disk_entry.split()[0]
        confirm = QMessageBox.question(self, "Confirm", f"Erase and install Ventoy on {device}?",
                                       QMessageBox.Yes | QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return

        with TemporaryDirectory() as tmpdir:
            self.progress.setValue(5)
            ventoy_tar = Path(tmpdir) / "ventoy.tar.gz"
            r = requests.get(VENTOY_RELEASE, stream=True)
            with open(ventoy_tar, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            self.progress.setValue(25)

            subprocess.run(["tar", "xf", str(ventoy_tar)], cwd=tmpdir)
            extracted = next(Path(tmpdir).glob("ventoy-*"))
            ventoy_script = extracted / "Ventoy2Disk.sh"
            cmd = ["sudo", str(ventoy_script), "-i", device]
            result = subprocess.run(cmd, input=b"y\n", capture_output=True)
            self.progress.setValue(80)
            if result.returncode == 0:
                QMessageBox.information(self, "Ventoy Installed", "Ventoy successfully installed.")
                self.progress.setValue(100)
            else:
                QMessageBox.critical(self, "Failed", result.stderr.decode())

    def download_and_copy_iso(self):
        iso_file = self.iso_select.currentText()
        if not iso_file:
            return
        iso_url = ALTIMA_ISO_LIST + iso_file
        self.progress.setValue(0)
        try:
            r = requests.get(iso_url, stream=True)
            iso_path = Path.home() / "Downloads" / iso_file
            with open(iso_path, "wb") as f:
                total = int(r.headers.get("content-length", 0))
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    self.progress.setValue(int(f.tell() / total * 100 * 0.5))
            self.progress.setValue(50)

            disk_entry = self.device_select.currentText()
            device = disk_entry.split()[0]
            mount_output = subprocess.check_output(["diskutil", "list", device]).decode()
            match = [line for line in mount_output.splitlines() if "Ventoy" in line]
            if not match:
                QMessageBox.critical(self, "Not Found", "Could not find mounted Ventoy partition.")
                return
            # Get mount path
            vol_output = subprocess.check_output(["diskutil", "info", "-plist", device + "s2"])
            from plistlib import loads
            vol_plist = loads(vol_output)
            mount_point = vol_plist.get("MountPoint")
            if not mount_point:
                QMessageBox.warning(self, "Mount Error", "Please replug the USB stick after installing Ventoy.")
                return

            # Copy ISO
            subprocess.run(["cp", str(iso_path), mount_point])
            self.progress.setValue(100)
            QMessageBox.information(self, "Done", f"{iso_file} copied to USB.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AltimaUSBFlasher()
    window.show()
    sys.exit(app.exec())
