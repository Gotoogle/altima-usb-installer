import sys
import subprocess
import traceback
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit
)
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtCore import Qt

# --- App Constants ---
ALTIMA_LOGO_PATH = "src/altima_usb_installer/altima-logo-100.png"
ALTIMA_ISO_LIST = "https://download.altimalinux.com/"
VENTOY_WIN_URL = "https://github.com/ventoy/Ventoy/releases/latest/download/ventoy-1.0.97-windows.zip"


class AltimaUSBInstaller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Altima USB Installer")
        self.setGeometry(200, 200, 500, 450)

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

        # --- Output Area ---
        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        layout.addWidget(self.output_area)

        # --- Scan Button ---
        self.scan_button = QPushButton("Scan for USB Devices")
        self.scan_button.clicked.connect(self.scan_usb_devices)
        layout.addWidget(self.scan_button)

        self.setLayout(layout)

    def scan_usb_devices(self):
        self.output_area.setPlainText("Scanning for USB devices... please wait.")
        try:
            if sys.platform.startswith("win"):
                try:
                    # PowerShell (Windows 8+)
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
                    # WMIC Fallback
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
