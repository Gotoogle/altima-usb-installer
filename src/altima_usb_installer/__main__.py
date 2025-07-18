import sys
import subprocess
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QComboBox
from PySide6.QtGui import QPixmap, QMovie, Qt
from PySide6.QtCore import QTimer, QThread, Signal

ALTIMA_LOGO_PATH = "altima-logo-100.png"


# ---------- Worker Thread for USB Scan ----------
class USBScanner(QThread):
    devices_found = Signal(list)

    def run(self):
        devices = []
        try:
            output = subprocess.check_output(
                ["wmic", "logicaldisk", "get", "DeviceID,VolumeName,Size,DriveType,Description"],
                text=True
            )
            for line in output.splitlines()[1:]:
                parts = [p.strip() for p in line.split() if p.strip()]
                if len(parts) >= 4:
                    device, label, size, dtype = parts[0], parts[1], parts[2], parts[3]
                    try:
                        size_gb = int(size) / (1024 ** 3)
                    except ValueError:
                        continue

                    if (dtype == "2" or "USB" in line) and size_gb > 8:
                        devices.append(f"{device} ({label}) {size_gb:.1f} GB")
            self.devices_found.emit(devices)
        except Exception:
            self.devices_found.emit([])


# ---------- Main Window (Minimal Diagnostic) ----------
class AltimaUSBInstaller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Altima USB Installer - Diagnostic v1.3.7")
        self.setMinimumWidth(400)

        # --- Logo ---
        self.logo = QLabel()
        self.logo.setAlignment(Qt.AlignCenter)
        self.logo.setPixmap(QPixmap(ALTIMA_LOGO_PATH).scaledToHeight(100))

        # --- Spinner ---
        self.spinner = QLabel()
        self.spinner.setAlignment(Qt.AlignCenter)
        self.spinner_movie = QMovie(self.get_spinner_gif())
        self.spinner.setMovie(self.spinner_movie)
        self.spinner_movie.start()

        # --- Status & Device List ---
        self.status_label = QLabel("Starting... UI should appear instantly.")
        self.device_select = QComboBox()

        # --- Layout ---
        layout = QVBoxLayout()
        layout.addWidget(self.logo)
        layout.addWidget(self.spinner)
        layout.addWidget(self.status_label)
        layout.addWidget(self.device_select)
        self.setLayout(layout)

        # ✅ Delay scanning until after UI fully shows
        QTimer.singleShot(1500, self.start_usb_scan)

    def get_spinner_gif(self):
        return str(Path(__file__).parent / "spinner.gif")

    def start_usb_scan(self):
        self.status_label.setText("Scanning USB sticks...")
        self.scanner_thread = USBScanner()
        self.scanner_thread.devices_found.connect(self.populate_usb_list)
        self.scanner_thread.start()

    def populate_usb_list(self, devices):
        self.spinner.hide()
        if not devices:
            self.status_label.setText("No USB sticks >8GB found.")
        else:
            self.status_label.setText("Select USB stick:")
            for d in devices:
                self.device_select.addItem(d)


def main():
    app = QApplication(sys.argv)
    window = AltimaUSBInstaller()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
