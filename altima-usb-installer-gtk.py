#!/usr/bin/env python3
import gi
import subprocess
import traceback
import requests
import zipfile
import os
import glob
import json
import shutil
import threading

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

# Only import WebKit2 on Linux/macOS - V2.06
if os.name != "nt":
    gi.require_version("WebKit2", "4.0")
    from gi.repository import WebKit2

# --- App Constants ---
ALTIMA_ISO_LIST = "https://download.altimalinux.com/altima-iso-list.json"
VENTOY_WIN_URL = "https://download.altimalinux.com/ventoy.zip"
VENTOY_DEST = "ventoy"

SLIDESHOW_IMAGES = [
    os.path.abspath("slide1.png"),
    os.path.abspath("slide2.png"),
    os.path.abspath("slide3.png")
]

SLIDESHOW_URLS = [
    "file://" + os.path.abspath("slide1.html"),
    "file://" + os.path.abspath("slide2.html"),
    "file://" + os.path.abspath("slide3.html")
]


class AltimaUSBInstaller(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="Altima USB Installer")
        self.set_default_size(950, 520)

        self.selected_usb = None
        self.current_slide = 0

        # Main horizontal box
        self.hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.hbox.set_margin_top(10)
        self.hbox.set_margin_bottom(10)
        self.hbox.set_margin_start(10)
        self.hbox.set_margin_end(10)
        self.add(self.hbox)

        # Left side (~30% width)
        self.left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.left_box.set_size_request(300, -1)
        self.hbox.pack_start(self.left_box, False, False, 0)

        # Right side (WebKit or static slideshow)
        if os.name != "nt":
            self.webview = WebKit2.WebView()
            self.webview.set_hexpand(True)
            self.webview.set_vexpand(True)
            self.hbox.pack_start(self.webview, True, True, 0)
        else:
            self.image_slide = Gtk.Image()
            self.hbox.pack_start(self.image_slide, True, True, 0)

        self.start_slideshow()
        self.init_usb_screen()

    # -----------------------------
    # Slideshow
    # -----------------------------
    def start_slideshow(self):
        if os.name != "nt":
            self.webview.load_uri(SLIDESHOW_URLS[self.current_slide])
            GLib.timeout_add_seconds(5, self.rotate_slides)
        else:
            self.image_slide.set_from_file(SLIDESHOW_IMAGES[self.current_slide])
            GLib.timeout_add_seconds(5, self.rotate_slides)

    def rotate_slides(self):
        self.current_slide = (self.current_slide + 1) % (
            len(SLIDESHOW_URLS) if os.name != "nt" else len(SLIDESHOW_IMAGES)
        )
        if os.name != "nt":
            self.webview.load_uri(SLIDESHOW_URLS[self.current_slide])
        else:
            self.image_slide.set_from_file(SLIDESHOW_IMAGES[self.current_slide])
        return True

    # -----------------------------
    # Screen 1: USB Detection
    # -----------------------------
    def init_usb_screen(self):
        for child in self.left_box.get_children():
            self.left_box.remove(child)

        label = Gtk.Label(label="Insert USB stick and click Scan for USB Devices:")
        label.set_markup("<b>Insert USB stick and click Scan for USB Devices:</b>")
        self.left_box.pack_start(label, False, False, 0)

        self.textview = Gtk.TextView()
        self.textview.set_editable(False)
        self.textview.set_size_request(-1, 120)
        self.textbuffer = self.textview.get_buffer()
        self.left_box.pack_start(self.textview, False, False, 0)

        self.usb_listbox = Gtk.ListBox()
        self.left_box.pack_start(self.usb_listbox, True, True, 0)

        self.scan_button = Gtk.Button(label="Scan for USB Devices")
        self.scan_button.connect("clicked", self.scan_usb_devices)
        self.left_box.pack_start(self.scan_button, False, False, 0)

        self.ok_button = Gtk.Button(label="Prepare Ventoy")
        self.ok_button.connect("clicked", self.download_and_prepare_ventoy)
        self.ok_button.set_sensitive(False)
        self.left_box.pack_start(self.ok_button, False, False, 0)

        self.show_all()

    def scan_usb_devices(self, widget):
        self.textbuffer.set_text("Scanning for USB devices... please wait.")
        self.usb_listbox.foreach(lambda w: self.usb_listbox.remove(w))

        def scan():
            try:
                output_lines = []
                if os.name == "nt":
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
                else:
                    raw = subprocess.check_output(
                        ["lsblk", "-o", "NAME,SIZE,MODEL,TRAN"], text=True
                    )
                    for l in raw.splitlines():
                        if "usb" in l.lower():
                            cols = l.split()
                            if len(cols) >= 3:
                                name, size, model = cols[0], cols[1], cols[2]
                                output_lines.append(f"{name} | {model} | {size}")

                clean_output = "\n".join(output_lines) if output_lines else "No USB devices detected."
                GLib.idle_add(self.textbuffer.set_text, clean_output)

                for line in output_lines:
                    row = Gtk.ListBoxRow()
                    row.add(Gtk.Label(label=line))
                    GLib.idle_add(self.usb_listbox.add, row)

                if output_lines:
                    GLib.idle_add(self.ok_button.set_sensitive, True)
                GLib.idle_add(self.show_all)
            except Exception:
                GLib.idle_add(self.textbuffer.set_text, traceback.format_exc())

        threading.Thread(target=scan, daemon=True).start()

    # -----------------------------
    # Screen 2: Ventoy Preparation
    # -----------------------------
    def download_and_prepare_ventoy(self, widget):
        selected = self.usb_listbox.get_selected_row()
        if not selected:
            self.textbuffer.set_text("Please select a USB device first.")
            return

        self.selected_usb = selected.get_child().get_text()
        self.textbuffer.set_text(f"Selected: {self.selected_usb}\nDownloading Ventoy...")

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
                                    GLib.idle_add(
                                        self.textbuffer.set_text,
                                        f"Downloading Ventoy... {percent:.2f}%"
                                    )

                with zipfile.ZipFile(ventoy_zip_path, "r") as zip_ref:
                    zip_ref.extractall(VENTOY_DEST)

                GLib.idle_add(self.textbuffer.set_text, "✅ Ventoy downloaded. Running Ventoy2Disk...")

                ventoy_folders = glob.glob(os.path.join(VENTOY_DEST, "ventoy-*"))
                if ventoy_folders:
                    ventoy_exe = os.path.join(ventoy_folders[0], "Ventoy2Disk.exe")
                    if os.path.exists(ventoy_exe) and os.name == "nt":
                        subprocess.run(
                            ["powershell", "Start-Process", ventoy_exe, "-Verb", "runAs"],
                            check=True
                        )
                        GLib.idle_add(self.goto_iso_screen)
                    elif os.name != "nt":
                        GLib.idle_add(self.goto_iso_screen)
                    else:
                        GLib.idle_add(self.textbuffer.set_text, "❌ Ventoy2Disk.exe not found.")
                else:
                    GLib.idle_add(self.textbuffer.set_text, "❌ Ventoy folder not found.")
            except Exception:
                GLib.idle_add(self.textbuffer.set_text, traceback.format_exc())

        threading.Thread(target=download_and_run, daemon=True).start()

    # -----------------------------
    # Screen 3: ISO Download & Auto-Copy
    # -----------------------------
    def goto_iso_screen(self):
        for child in self.left_box.get_children():
            self.left_box.remove(child)

        label = Gtk.Label(
            label=f"Ventoy installed on: {self.selected_usb}\nSelect an ISO to download:"
        )
        label.set_markup(f"<b>Ventoy installed on: {self.selected_usb}</b>\nSelect an ISO to download:")
        self.left_box.pack_start(label, False, False, 0)

        self.iso_listbox = Gtk.ListBox()
        self.left_box.pack_start(self.iso_listbox, True, True, 0)

        self.output_area = Gtk.TextView()
        self.output_area.set_editable(False)
        self.output_buffer = self.output_area.get_buffer()
        self.left_box.pack_start(self.output_area, True, True, 0)

        # ✅ Auto-eject checkbox
        self.eject_checkbox = Gtk.CheckButton(label="Eject USB when complete")
        self.eject_checkbox.set_active(True)
        self.left_box.pack_start(self.eject_checkbox, False, False, 0)

        self.progress_bar = Gtk.ProgressBar()
        self.left_box.pack_start(self.progress_bar, False, False, 0)

        self.download_iso_button = Gtk.Button(label="Download & Copy ISO")
        self.download_iso_button.connect("clicked", self.download_iso)
        self.left_box.pack_start(self.download_iso_button, False, False, 0)

        self.show_all()
        self.load_iso_list()

    def load_iso_list(self):
        self.output_buffer.set_text("Fetching ISO list...")

        def fetch_list():
            try:
                response = requests.get(ALTIMA_ISO_LIST, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                else:
                    data = {}

                isos = data.get("isos", [
                    {"name": "Altima Linux Minimal (Fallback)", "file": "altima-minimal-1.0.iso"},
                    {"name": "Altima Linux Full (Fallback)", "file": "altima-full-1.0.iso"}
                ])

                GLib.idle_add(self.iso_listbox.foreach, lambda w: self.iso_listbox.remove(w))
                for iso in isos:
                    row = Gtk.ListBoxRow()
                    row.add(Gtk.Label(label=f"{iso['name']} ({iso['file']})"))
                    GLib.idle_add(self.iso_listbox.add, row)
                GLib.idle_add(self.show_all)
            except Exception:
                GLib.idle_add(self.output_buffer.set_text, traceback.format_exc())

        threading.Thread(target=fetch_list, daemon=True).start()

    def download_iso(self, widget):
        selected = self.iso_listbox.get_selected_row()
        if not selected:
            self.output_buffer.set_text("Please select an ISO first.")
            return

        iso_text = selected.get_child().get_text()
        iso_file = iso_text.split("(")[-1].strip(")")
        self.output_buffer.set_text(f"Downloading {iso_file}...")

        def download_and_copy():
            try:
                iso_url = ALTIMA_ISO_LIST.replace("altima-iso-list.json", iso_file)
                iso_path = os.path.join(os.getcwd(), iso_file)

                # ✅ Download with progress bar
                with requests.get(iso_url, stream=True, timeout=10) as r:
                    r.raise_for_status()
                    total = int(r.headers.get("content-length", 0))
                    downloaded = 0
                    with open(iso_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total > 0:
                                    fraction = downloaded / total
                                    GLib.idle_add(self.progress_bar.set_fraction, fraction)
                                    GLib.idle_add(self.progress_bar.set_text, f"{fraction*100:.1f}%")

                # ✅ Copy to USB
                copied_path = None
                if os.name == "nt":
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
                    except Exception:
                        pass
                else:
                    possible_mounts = []
                    for base in ["/media", "/run/media"]:
                        if os.path.exists(base):
                            for root, dirs, _ in os.walk(base):
                                for d in dirs:
                                    if "ventoy" in d.lower():
                                        possible_mounts.append(os.path.join(root, d))
                    if possible_mounts:
                        copied_path = os.path.join(possible_mounts[0], iso_file)
                        shutil.copy(iso_path, copied_path)

                if copied_path:
                    GLib.idle_add(
                        self.output_buffer.set_text,
                        f"✅ ISO copied to {copied_path}\nYour USB is ready to boot!"
                    )
                    if self.eject_checkbox.get_active():
                        self.eject_usb(copied_path)
                else:
                    GLib.idle_add(
                        self.output_buffer.set_text,
                        f"✅ ISO downloaded to {iso_path}\nCopy manually if needed."
                    )
            except Exception:
                GLib.idle_add(self.output_buffer.set_text, traceback.format_exc())
            finally:
                GLib.idle_add(self.progress_bar.set_fraction, 0)
                GLib.idle_add(self.progress_bar.set_text, "")

        threading.Thread(target=download_and_copy, daemon=True).start()

    def eject_usb(self, copied_path):
        try:
            if os.name == "nt":
                drive = copied_path.split(":")[0]
                subprocess.run(
                    [
                        "powershell", "-NoLogo", "-NoProfile",
                        f"Remove-Volume -DriveLetter {drive} -Confirm:$false"
                    ],
                    check=True
                )
            else:
                # Attempt to unmount & power off
                mount = copied_path.split("/")[2]
                subprocess.run(["udisksctl", "unmount", "-b", f"/dev/{mount}"])
                subprocess.run(["udisksctl", "power-off", "-b", f"/dev/{mount}"])
            GLib.idle_add(self.output_buffer.set_text, "✅ USB ejected safely.")
        except Exception:
            GLib.idle_add(
                self.output_buffer.set_text,
                self.output_buffer.get_text(self.output_buffer.get_start_iter(),
                                            self.output_buffer.get_end_iter(), True)
                + "\n⚠️ Could not auto-eject USB."
            )


def main():
    win = AltimaUSBInstaller()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
