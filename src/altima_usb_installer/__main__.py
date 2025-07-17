import sys
import subprocess
import traceback
import requests
import zipfile
import os

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit
)
from PySide6.QtGui import QFont, QPixmap, QMovie
from PySide6.QtCore import Qt

# --- App Constants ---
ALTIMA_LOGO_PATH = "src/altima_usb_installer/altima-logo-100.png"
SPINNER_PATH = "src/altima_usb_installer/spinner.gif"
ALTIMA_ISO_LIST = "https://download.altimalinux.com/"
VENTOY_WIN_URL = "https://github.com/ventoy/Ventoy/releases/latest/download/ventoy-1.0.97-windows.zip"
VENTOY_DEST = "ventoy"  # folder where Ventoy will be extracted


class AltimaUSBInstaller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Altima USB Installer")
        self.setGeometry(200, 200, 500, 500)

        layout = QVBoxLayout()

        # --- Logo ---
        try:
            pixmap = QPixmap(ALTIMA_LOGO_PATH)
            logo_label = QLabel()
            logo_label.setPixmap(pixmap.scaled(100, 100, Qt.KeepAspectRatio))
            logo_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(logo_label)
        except Exception:
            pass

        # --- Instructions ---
        self.info_label = QLabel("Insert a USB stick, then click 'Scan for USB Devices'.")
        self.info_label.setFont(QFont("Arial", 11))
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)

        # --- Spinner (hidden by default) ---
        self.spinner_label = QLabel()
        self.spinner_movie = QMovie(SPINNER_PATH)
        self.spinner_label.setMovie(self.spinner_movie)
        self.spinner_label.setAlignment(Qt.AlignCenter)
        self.spinner_label.setVisible(False)
        layout.addWidget(self.spinner_label)

        # --- Output Area ---
        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        layout.addWidget(self.output_area)

        # --- Buttons ---
        self.scan_button = QPushButton("Scan for USB Devices")
        self.scan_button.clicked.connect(self.scan_usb_devices)
        layout.addWidget(self.scan_button)

        self.download_ventoy_button = QPushButton("Download Ventoy")
        self.download_ventoy_button.clicked.connect(self.download_and_extract_ventoy)
        layout.addWidget(self.download_ventoy_button)

        self.setLayout(layout)

    # =========================
    # USB DEVICE SCAN
    # =========================
    def scan_usb_devices(self):
        self.output_area.setPlainText("Scanning for USB devices... please wait.")
        self.spinner_label.setVisible(True)
        self.spinner_movie.start()

        QApplication.processEvents()  # Refresh UI immediately

        try:
            if sys.platform.startswith("win"):
                try:
                    # ✅ PowerShell (Windows 8+)
                    output = subprocess.check_output(
                        [
                            "powershell", "-Command",
                            "Get-Disk | Where-Object {$_.BusType -eq 'USB'} "
                            "| Select-Object -Property Number, FriendlyName, Size, BusType "
                            "| Format-Table -AutoSize"
                        ],
                        text=True
                    )
                except Exception:
                    # ✅ WMIC fallback
                    output = subprocess.check_output(
                        [
                            "wmic", "diskdrive", "where", "InterfaceType='USB'",
                            "get", "Caption,DeviceID,Size"
                        ],
                        text=True
                    )
            elif sys.platform.startswith("linux"):
                output = subprocess.check_output(
                    ["lsblk", "-o", "NAME,SIZE,MODEL,TRAN"], text=True
                )
            else:
                output = "Unsupported platform."

            self.output_area.setPlainText(output.strip())
        except Exception:
            error_msg = f"Error scanning USB devices:\n{traceback.format_exc()}"
            self.output_area.setPlainText(error_msg)
        finally:
            self.spinner_movie.stop()
            self.spinner_label.setVisible(False)

    # =========================
    # DOWNLOAD & EXTRACT VENTOY
    # =========================
    def download_and_extract_ventoy(self):
        self.output_area.setPlainText("Downloading Ventoy... please wait.")
        self.spinner_label.setVisible(True)
        self.spinner_movie.start()
        QApplication.processEvents()

        try:
            os.makedirs(VENTOY_DEST, exist_ok=True)
            ventoy_zip_path = os.path.join(VENTOY_DEST, "ventoy.zip")

            # Download Ventoy
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

            # Extract Ventoy
            with zipfile.ZipFile(ventoy_zip_path, "r") as zip_ref:
                zip_ref.extractall(VENTOY_DEST)

            self.output_area.setPlainText("✅ Ventoy downloaded and extracted successfully!")
        except Exception:
            error_msg = f"Error downloading Ventoy:\n{traceback.format_exc()}"
            self.output_area.setPlainText(error_msg)
        finally:
            self.spinner_movie.stop()
            self.spinner_label.setVisible(False)


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
