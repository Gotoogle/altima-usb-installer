import sys
import subprocess
import traceback
import requests
import zipfile
import os
import time

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit, QHBoxLayout
)
from PySide6.QtGui import QFont, QPixmap, QMovie
from PySide6.QtCore import Qt, QTimer

# WebKit imports
from PySide6.QtWebEngineWidgets import QWebEngineView

# --- App Constants ---
ALTIMA_LOGO_PATH = "src/altima_usb_installer/altima-logo-100.png"
SPINNER_PATH = "src/altima_usb_installer/spinner.gif"
ALTIMA_ISO_LIST = "https://download.altimalinux.com/"
VENTOY_WIN_URL = "https://downloads.altimalinux.com/ventoy.zip"
VENTOY_DEST = "ventoy"  # folder where Ventoy will be extracted

# Slideshow URLs (placeholders)
SLIDESHOW_URLS = [
    "https://altimalinux.com/about",
    "https://altimalinux.com/about",
    "https://altimalinux.com/about"
]


class SplashScreen(QWidget):
    """Initial splash screen with logo and spinner."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Altima USB Installer")
        self.setGeometry(300, 300, 300, 200)
        layout = QVBoxLayout()

        try:
            pixmap = QPixmap(ALTIMA_LOGO_PATH)
            logo_label = QLabel()
            logo_label.setPixmap(pixmap.scaled(100, 100, Qt.KeepAspectRatio))
            logo_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(logo_label)
        except Exception:
            pass

        self.spinner_label = QLabel()
        self.spinner_movie = QMovie(SPINNER_PATH)
        self.spinner_label.setMovie(self.spinner_movie)
        self.spinner_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.spinner_label)

        self.setLayout(layout)
        self.spinner_movie.start()


class AltimaUSBInstaller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Altima USB Installer")
        self.setGeometry(200, 200, 800, 500)  # Wider for WebKit panel
        self.current_slide = 0
        self.init_usb_screen()

    # =========================
    # SCREEN 1: USB Detection
    # =========================
    def init_usb_screen(self):
        self.layout = QHBoxLayout()

        # Left: main controls
        left_layout = QVBoxLayout()

        title = QLabel("Detected USB Devices")
        title.setFont(QFont("Arial", 12, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(title)

        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        left_layout.addWidget(self.output_area)

        self.scan_button = QPushButton("Scan for USB Devices")
        self.scan_button.clicked.connect(self.scan_usb_devices)
        left_layout.addWidget(self.scan_button)

        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.goto_ventoy_screen)
        self.ok_button.setEnabled(False)
        left_layout.addWidget(self.ok_button)

        self.layout.addLayout(left_layout)

        # Right: WebKit panel
        self.webview = QWebEngineView()
        self.webview.setUrl(SLIDESHOW_URLS[0])
        self.layout.addWidget(self.webview)

        self.setLayout(self.layout)

        # Timer for slideshow rotation
        self.timer = QTimer()
        self.timer.timeout.connect(self.rotate_slides)
        self.timer.start(5000)  # rotate every 5s

    def rotate_slides(self):
        self.current_slide = (self.current_slide + 1) % len(SLIDESHOW_URLS)
        self.webview.setUrl(SLIDESHOW_URLS[self.current_slide])

    def scan_usb_devices(self):
        self.output_area.setPlainText("Scanning for USB devices... please wait.")
        QApplication.processEvents()

        try:
            if sys.platform.startswith("win"):
                try:
                    output = subprocess.check_output(
                        [
                            "powershell",
                            "-NoLogo", "-NoProfile",
                            "-WindowStyle", "Normal",
                            "-Command",
                            "mode con: cols=50 lines=15; "
                            "Get-Disk | Where-Object {$_.BusType -eq 'USB'} "
                            "| Select-Object -Property Number, FriendlyName, Size, BusType "
                            "| Format-Table -AutoSize"
                        ],
                        text=True
                    )
                except Exception:
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
            if "USB" in output or "usb" in output.lower():
                self.ok_button.setEnabled(True)
        except Exception:
            self.output_area.setPlainText(f"Error scanning USB devices:\n{traceback.format_exc()}")

    # =========================
    # SCREEN 2: Ventoy Download
    # =========================
    def goto_ventoy_screen(self):
        for i in reversed(range(self.layout.count())):
            widget = self.layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        ventoy_layout = QVBoxLayout()

        title = QLabel("Prepare Ventoy on Selected USB")
        title.setFont(QFont("Arial", 12, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        ventoy_layout.addWidget(title)

        ventoy_url_label = QLabel(f"Ventoy Download URL:\n{VENTOY_WIN_URL}")
        ventoy_url_label.setAlignment(Qt.AlignCenter)
        ventoy_layout.addWidget(ventoy_url_label)

        self.download_button = QPushButton("Download Ventoy")
        self.download_button.clicked.connect(self.download_and_extract_ventoy)
        ventoy_layout.addWidget(self.download_button)

        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        ventoy_layout.addWidget(self.output_area)

        self.setLayout(ventoy_layout)

    def download_and_extract_ventoy(self):
        self.output_area.setPlainText("Downloading Ventoy... please wait.")
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

            self.output_area.setPlainText("✅ Ventoy downloaded and extracted successfully!")
        except Exception:
            self.output_area.setPlainText(f"Error downloading Ventoy:\n{traceback.format_exc()}")


def main():
    app = QApplication(sys.argv)

    splash = SplashScreen()
    splash.show()
    app.processEvents()
    time.sleep(2)
    splash.close()

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
