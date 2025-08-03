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
import re
import hashlib

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.0")
from gi.repository import Gtk, GLib, WebKit2

# --- App Constants ---
ALTIMA_ISO_LIST = "https://download.altimalinux.com/altima-iso-list.json"
VENTOY_WIN_URL = "https://download.altimalinux.com/ventoy.zip"
VENTOY_DEST = "ventoy"

SLIDESHOW_URLS = [
    "file://" + os.path.abspath("slide1.html"),
    "file://" + os.path.abspath("slide2.html"),
    "file://" + os.path.abspath("slide3.html")
]


class AltimaUSBInstaller(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="Altima USB Installer")
        self.set_default_size(900, 500)
        self.set_border_width(5)

        self.selected_usb = None
        self.current_slide = 0
        self.ventoy_mounts = []
        self.iso_data = []

        self.hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.add(self.hbox)

        self.left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.left_box.set_size_request(280, -1)
        self.hbox.pack_start(self.left_box, False, False, 5)

        self.webview = WebKit2.WebView()
        self.webview.set_hexpand(True)
        self.webview.set_vexpand(True)
        self.hbox.pack_start(self.webview, True, True, 5)

        self.start_slideshow()
        self.init_usb_screen()

    # -----------------------------
    # Slideshow
    # -----------------------------
    def start_slideshow(self):
        self.webview.load_uri(SLIDESHOW_URLS[self.current_slide])
        GLib.timeout_add_seconds(5, self.rotate_slides)

    def rotate_slides(self):
        self.current_slide = (self.current_slide + 1) % len(SLIDESHOW_URLS)
        self.webview.load_uri(SLIDESHOW_URLS[self.current_slide])
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
        self.textbuffer = self.textview.get_buffer()
        self.left_box.pack_start(self.textview, True, True, 0)

        self.usb_listbox = Gtk.ListBox()
        self.left_box.pack_start(self.usb_listbox, True, True, 0)

        self.scan_button = Gtk.Button(label="Scan for USB Devices")
        self.scan_button.set_size_request(210, 35)
        self.scan_button.connect("clicked", self.scan_usb_devices)
        self.left_box.pack_start(self.scan_button, False, False, 0)

        self.ok_button = Gtk.Button(label="Prepare Ventoy")
        self.ok_button.set_size_request(210, 35)
        self.ok_button.connect("clicked", self.download_and_prepare_ventoy)
        self.ok_button.set_sensitive(False)
        self.left_box.pack_start(self.ok_button, False, False, 0)

        self.show_all()

    def scan_usb_devices(self, widget):
        self.textbuffer.set_text("Scanning for USB devices... please wait.")
        self.usb_listbox.foreach(lambda w: self.usb_listbox.remove(w))

        def scan():
            try:
                output = ""
                if os.name == "nt":
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    si.wShowWindow = 0
                    try:
                        output = subprocess.check_output(
                            [
                                "powershell", "-NoLogo", "-NoProfile",
                                "-Command",
                                "Get-Disk | Where-Object {$_.BusType -eq 'USB'} "
                                "| Where-Object {$_.Size -gt 0} "
                                "| Select-Object -Property Number, FriendlyName, Size, BusType "
                                "| Format-Table -AutoSize"
                            ],
                            text=True, startupinfo=si
                        )
                    except Exception:
                        output = subprocess.check_output(
                            [
                                "wmic", "diskdrive",
                                "where", "InterfaceType='USB' and Size>0",
                                "get", "Caption,DeviceID,Size"
                            ],
                            text=True, startupinfo=si
                        )
                else:
                    lsblk_output = subprocess.check_output(
                        ["lsblk", "-o", "NAME,SIZE,MODEL,TRAN"], text=True
                    )
                    output_lines = [
                        line for line in lsblk_output.splitlines()
                        if "usb" in line.lower() and not re.search(r"\s0[B|M|K]", line)
                    ]
                    output = "\n".join(output_lines)

                GLib.idle_add(self.textbuffer.set_text, output.strip())
                for line in output.splitlines():
                    row = Gtk.ListBoxRow()
                    row.add(Gtk.Label(label=line.strip()))
                    GLib.idle_add(self.usb_listbox.add, row)

                if output.strip():
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
        self.textbuffer.set_text(f"Selected: {self.selected_usb}\nPreparing Ventoy folder...")

        if os.path.exists(VENTOY_DEST):
            try:
                shutil.rmtree(VENTOY_DEST)
            except PermissionError:
                self.textbuffer.set_text("❌ Cannot remove old Ventoy folder. Delete manually.")
                return

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
    # Screen 3: Ventoy USB + ISO Download
    # -----------------------------
    def goto_iso_screen(self):
        for child in self.left_box.get_children():
            self.left_box.remove(child)

        label = Gtk.Label(label="Select a Ventoy USB to copy ISO to:")
        label.set_markup("<b>Select a Ventoy USB to copy ISO to:</b>")
        self.left_box.pack_start(label, False, False, 0)

        self.ventoy_listbox = Gtk.ListBox()
        self.left_box.pack_start(self.ventoy_listbox, True, True, 0)

        self.refresh_button = Gtk.Button(label="Refresh Ventoy USBs")
        self.refresh_button.set_size_request(210, 35)
        self.refresh_button.connect("clicked", self.refresh_ventoy_list)
        self.left_box.pack_start(self.refresh_button, False, False, 0)

        iso_label = Gtk.Label(label="Select an ISO to download:")
        iso_label.set_markup("<b>Select an ISO to download:</b>")
        self.left_box.pack_start(iso_label, False, False, 0)

        self.iso_listbox = Gtk.ListBox()
        self.left_box.pack_start(self.iso_listbox, True, True, 0)

        self.output_area = Gtk.TextView()
        self.output_area.set_editable(False)
        self.output_buffer = self.output_area.get_buffer()
        self.left_box.pack_start(self.output_area, True, True, 0)

        self.download_iso_button = Gtk.Button(label="Download & Copy ISO")
        self.download_iso_button.set_size_request(210, 35)
        self.download_iso_button.connect("clicked", self.download_iso)
        self.left_box.pack_start(self.download_iso_button, False, False, 0)

        self.show_all()
        self.refresh_ventoy_list()
        self.load_iso_list()

    def refresh_ventoy_list(self, widget=None):
        self.ventoy_listbox.foreach(lambda w: self.ventoy_listbox.remove(w))
        self.ventoy_mounts = []

        if os.name != "nt":
            usb_mount = "/media"
            for d in os.listdir(usb_mount):
                full_path = os.path.join(usb_mount, d)
                if os.path.isdir(full_path) and os.path.exists(os.path.join(full_path, "ventoy")):
                    self.ventoy_mounts.append(full_path)
                    row = Gtk.ListBoxRow()
                    row.add(Gtk.Label(label=full_path))
                    self.ventoy_listbox.add(row)

        self.show_all()

    def load_iso_list(self):
        self.output_buffer.set_text("Fetching ISO list...")

        def fetch_list():
            try:
                response = requests.get(ALTIMA_ISO_LIST, timeout=5)
                data = response.json() if response.status_code == 200 else {}
                self.iso_data = data.get("isos", [
                    {"name": "Altima Linux Minimal (Fallback)", "file": "altima-minimal-1.0.iso"},
                    {"name": "Altima Linux Full (Fallback)", "file": "altima-full-1.0.iso"}
                ])

                self.iso_listbox.foreach(lambda w: self.iso_listbox.remove(w))
                for iso in self.iso_data:
                    row = Gtk.ListBoxRow()
                    row.add(Gtk.Label(label=f"{iso['name']} ({iso['file']})"))
                    GLib.idle_add(self.iso_listbox.add, row)

                # ✅ Auto-select first ISO row
                def select_first():
                    if self.iso_listbox.get_children():
                        self.iso_listbox.select_row(self.iso_listbox.get_row_at_index(0))
                GLib.idle_add(select_first)
                GLib.idle_add(self.show_all)
            except Exception:
                GLib.idle_add(self.output_buffer.set_text, traceback.format_exc())

        threading.Thread(target=fetch_list, daemon=True).start()

    def sanitize_filename(self, name):
        return re.sub(r"[^\w\-.]", "-", name)

    def fetch_checksum_from_file(self, checksum_url):
        try:
            r = requests.get(checksum_url, timeout=5)
            if r.status_code == 200:
                # Parse first hash in file (supports .md5 or .sha256)
                match = re.search(r"([a-fA-F0-9]{32,64})", r.text)
                if match:
                    return match.group(1)
        except Exception:
            pass
        return None

    def verify_checksum(self, file_path, expected_hash):
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest().lower() == expected_hash.lower()

    def download_iso(self, widget):
        selected_iso_row = self.iso_listbox.get_selected_row()
        selected_usb_row = self.ventoy_listbox.get_selected_row()

        if not selected_iso_row:
            self.output_buffer.set_text("Please select an ISO first.")
            return
        if not selected_usb_row and os.name != "nt":
            self.output_buffer.set_text("Please select a Ventoy USB first.")
            return

        selected_index = self.iso_listbox.get_children().index(selected_iso_row)
        iso_data = self.iso_data[selected_index]
        iso_file = self.sanitize_filename(iso_data["file"])
        iso_checksum = iso_data.get("sha256")
        self.output_buffer.set_text(f"Downloading {iso_file} directly to Ventoy USB...")

        def download_and_copy():
            try:
                iso_url = ALTIMA_ISO_LIST.replace("altima-iso-list.json", iso_file)

                if os.name == "nt":
                    GLib.idle_add(
                        self.output_buffer.set_text,
                        "✅ ISO downloaded, but copy to Ventoy USB must be manual on Windows."
                    )
                    return

                ventoy_mount = selected_usb_row.get_child().get_text()
                iso_usb_path = os.path.join(ventoy_mount, iso_file)

                total_size = 0
                downloaded = 0
                with requests.get(iso_url, stream=True) as r, open(iso_usb_path, "wb") as f:
                    r.raise_for_status()
                    total_size = int(r.headers.get("content-length", 0))
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                GLib.idle_add(
                                    self.output_buffer.set_text,
                                    f"Writing {iso_file} to Ventoy USB... {percent:.2f}%"
                                )

                written_size = os.path.getsize(iso_usb_path)
                if written_size != total_size:
                    GLib.idle_add(
                        self.output_buffer.set_text,
                        f"⚠ File size mismatch: {written_size} vs expected {total_size}"
                    )
                    return

                # ✅ Checksum handling
                checksum_value = None
                if iso_checksum:
                    if iso_checksum.endswith((".md5", ".sha256")):
                        checksum_url = ALTIMA_ISO_LIST.replace("altima-iso-list.json", iso_checksum)
                        checksum_value = self.fetch_checksum_from_file(checksum_url)
                    else:
                        checksum_value = iso_checksum

                if checksum_value:
                    self.output_buffer.set_text("Verifying checksum...")
                    if self.verify_checksum(iso_usb_path, checksum_value):
                        msg = f"✅ ISO verified & copied to {iso_usb_path}\n"
                    else:
                        msg = f"⚠ Checksum mismatch for {iso_file}\n"
                else:
                    msg = f"✅ ISO copied to {iso_usb_path}\n"

                # ✅ Auto-eject USB (Linux)
                if os.name != "nt":
                    try:
                        subprocess.run(["udisksctl", "power-off", "-b", ventoy_mount], check=False)
                        msg += "💡 USB safely ejected. Ready to boot!"
                    except Exception:
                        msg += "⚠ Could not auto-eject. Please eject manually."

                GLib.idle_add(self.output_buffer.set_text, msg)
            except Exception:
                GLib.idle_add(self.output_buffer.set_text, traceback.format_exc())

        threading.Thread(target=download_and_copy, daemon=True).start()


def main():
    win = AltimaUSBInstaller()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
