#!/usr/bin/env python3
"""
Argus PII Guard Native Installer & Windows Setup Wizard
Cross-platform desktop installation, upgrade, & integration script for Windows, macOS, and Linux.

Usage:
    python native_installer.py [options]

Options:
    --install           Perform application installation/upgrade via CLI
    --upgrade           Upgrade an existing installation via CLI
    --uninstall         Perform clean uninstallation via CLI
    --cli               Force command-line interactive mode (bypass GUI wizard)
    --target-dir DIR    Specify custom target directory
    --user-scope        Install in user-level directory (no admin/root required)
    --no-path           Do not modify system/user PATH environment variable
    --quiet             Run non-interactively
    --help              Show this help message
"""

import sys
import os
import argparse
import threading
import subprocess
import ctypes
from pathlib import Path

# Add project root to sys.path to allow importing backend.installer
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from backend.installer import (
        InstallerEngine,
        UninstallerEngine,
        get_default_install_path,
        check_privileges,
        elevate_privileges,
        close_running_app_processes,
        VERSION,
        APP_NAME
    )
except ImportError:
    parent_dir = Path(__file__).resolve().parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))
    from backend.installer import (
        InstallerEngine,
        UninstallerEngine,
        get_default_install_path,
        check_privileges,
        elevate_privileges,
        close_running_app_processes,
        VERSION,
        APP_NAME
    )


def run_gui_wizard():
    """Launch modern Windows Graphical Setup Wizard using Tkinter."""
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
    except ImportError:
        print("[!] Tkinter is not available. Falling back to command-line mode.")
        return False

    root = tk.Tk()
    root.title(f"{APP_NAME} v{VERSION} Setup Wizard")
    root.geometry("640x480")
    root.resizable(False, False)

    # Configure styles
    style = ttk.Style()
    style.theme_use("clam")
    
    bg_dark = "#1e293b"
    bg_light = "#f8fafc"
    accent_blue = "#2563eb"
    text_dark = "#0f172a"
    text_muted = "#475569"

    # Header Frame (Dark Banner)
    header_frame = tk.Frame(root, bg=bg_dark, height=75)
    header_frame.pack(fill="x", side="top")
    header_frame.pack_propagate(False)

    is_admin_active = False
    try:
        if sys.platform == "win32":
            is_admin_active = ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            is_admin_active = (os.geteuid() == 0)
    except Exception:
        is_admin_active = False

    admin_badge = " [Administrator]" if is_admin_active else ""

    header_title = tk.Label(
        header_frame,
        text=f"🛡️  {APP_NAME} v{VERSION} Setup{admin_badge}",
        font=("Segoe UI", 16, "bold"),
        fg="#ffffff",
        bg=bg_dark,
        anchor="w"
    )
    header_title.pack(padx=20, pady=(12, 2), fill="x")

    header_subtitle = tk.Label(
        header_frame,
        text="On-Device PII Detection & Remediation Sentinel",
        font=("Segoe UI", 10),
        fg="#94a3b8",
        bg=bg_dark,
        anchor="w"
    )
    header_subtitle.pack(padx=20, fill="x")

    # Content Container Frame
    container = tk.Frame(root, bg=bg_light)
    container.pack(fill="both", expand=True)

    # State variables
    action_var = tk.StringVar(value="install")
    scope_var = tk.StringVar(value="system")
    target_path_var = tk.StringVar(value=str(get_default_install_path(user_scope=False)))
    desktop_shortcut_var = tk.BooleanVar(value=True)
    start_shortcut_var = tk.BooleanVar(value=True)
    add_path_var = tk.BooleanVar(value=True)
    launch_after_var = tk.BooleanVar(value=True)

    # Pages Dict
    pages = {}

    # --- Page 1: Welcome & Action Selection ---
    page1 = tk.Frame(container, bg=bg_light)
    pages["welcome"] = page1

    lbl_welcome = tk.Label(
        page1,
        text="Welcome to the Argus PII Guard Setup Wizard",
        font=("Segoe UI", 13, "bold"),
        fg=text_dark,
        bg=bg_light,
        anchor="w"
    )
    lbl_welcome.pack(padx=25, pady=(20, 10), fill="x")

    lbl_desc = tk.Label(
        page1,
        text="This wizard will guide you through installing or upgrading Argus PII Guard on your system.\nSelect an action to proceed:",
        font=("Segoe UI", 10),
        fg=text_muted,
        bg=bg_light,
        justify="left",
        anchor="w"
    )
    lbl_desc.pack(padx=25, pady=(0, 15), fill="x")

    def update_default_path():
        is_user = (scope_var.get() == "user")
        target_path_var.set(str(get_default_install_path(user_scope=is_user)))

    rb_install = ttk.Radiobutton(
        page1,
        text="Install / Upgrade Argus PII Guard (Recommended)",
        variable=action_var,
        value="install"
    )
    rb_install.pack(padx=35, pady=5, anchor="w")

    rb_uninstall = ttk.Radiobutton(
        page1,
        text="Uninstall Argus PII Guard from this computer",
        variable=action_var,
        value="uninstall"
    )
    rb_uninstall.pack(padx=35, pady=5, anchor="w")

    # --- Page 2: Options & Destination ---
    page2 = tk.Frame(container, bg=bg_light)
    pages["options"] = page2

    lbl_opts_title = tk.Label(
        page2,
        text="Select Installation Location & Options",
        font=("Segoe UI", 12, "bold"),
        fg=text_dark,
        bg=bg_light,
        anchor="w"
    )
    lbl_opts_title.pack(padx=25, pady=(15, 10), fill="x")

    # Scope selection
    frame_scope = ttk.LabelFrame(page2, text=" Installation Scope ")
    frame_scope.pack(padx=25, pady=5, fill="x")

    rb_sys = ttk.Radiobutton(
        frame_scope,
        text="Install for all users (Administrator rights required)",
        variable=scope_var,
        value="system",
        command=update_default_path
    )
    rb_sys.pack(padx=15, pady=4, anchor="w")

    rb_usr = ttk.Radiobutton(
        frame_scope,
        text="Install for current user only (No elevation required)",
        variable=scope_var,
        value="user",
        command=update_default_path
    )
    rb_usr.pack(padx=15, pady=4, anchor="w")

    # Path selection
    frame_path = ttk.LabelFrame(page2, text=" Destination Directory ")
    frame_path.pack(padx=25, pady=8, fill="x")

    ent_path = ttk.Entry(frame_path, textvariable=target_path_var, width=50)
    ent_path.pack(side="left", padx=(10, 5), pady=8, fill="x", expand=True)

    def browse_folder():
        chosen = filedialog.askdirectory(initialdir=target_path_var.get())
        if chosen:
            target_path_var.set(chosen)

    btn_browse = ttk.Button(frame_path, text="Browse...", command=browse_folder)
    btn_browse.pack(side="right", padx=(0, 10), pady=8)

    # Shortcut options
    frame_flags = ttk.LabelFrame(page2, text=" Desktop Shortcuts & Integration ")
    frame_flags.pack(padx=25, pady=5, fill="x")

    chk_desktop = ttk.Checkbutton(frame_flags, text="Create Desktop Shortcut", variable=desktop_shortcut_var)
    chk_desktop.pack(padx=15, pady=3, anchor="w")

    chk_start = ttk.Checkbutton(frame_flags, text="Add to Start Menu Programs", variable=start_shortcut_var)
    chk_start.pack(padx=15, pady=3, anchor="w")

    chk_path = ttk.Checkbutton(frame_flags, text="Register application path in system PATH environment", variable=add_path_var)
    chk_path.pack(padx=15, pady=3, anchor="w")

    # --- Page 3: Installation Progress ---
    page3 = tk.Frame(container, bg=bg_light)
    pages["progress"] = page3

    lbl_prog_title = tk.Label(
        page3,
        text="Executing Setup Operations...",
        font=("Segoe UI", 12, "bold"),
        fg=text_dark,
        bg=bg_light,
        anchor="w"
    )
    lbl_prog_title.pack(padx=25, pady=(25, 10), fill="x")

    lbl_status_msg = tk.Label(
        page3,
        text="Preparing installation payload...",
        font=("Segoe UI", 10),
        fg=text_muted,
        bg=bg_light,
        anchor="w"
    )
    lbl_status_msg.pack(padx=25, pady=(0, 15), fill="x")

    progressbar = ttk.Progressbar(page3, mode="indeterminate", length=540)
    progressbar.pack(padx=25, pady=10)

    txt_log = tk.Text(page3, height=8, width=70, font=("Consolas", 9), state="disabled", bg="#ffffff", fg="#1e293b")
    txt_log.pack(padx=25, pady=10, fill="both", expand=True)

    def append_log(msg):
        txt_log.config(state="normal")
        txt_log.insert("end", msg + "\n")
        txt_log.see("end")
        txt_log.config(state="disabled")

    # --- Page 4: Completion ---
    page4 = tk.Frame(container, bg=bg_light)
    pages["complete"] = page4

    lbl_done_title = tk.Label(
        page4,
        text="🎉 Setup Completed Successfully!",
        font=("Segoe UI", 14, "bold"),
        fg="#16a34a",
        bg=bg_light,
        anchor="w"
    )
    lbl_done_title.pack(padx=25, pady=(25, 10), fill="x")

    lbl_done_msg = tk.Label(
        page4,
        text="Argus PII Guard has been successfully deployed and registered on your computer.",
        font=("Segoe UI", 10),
        fg=text_dark,
        bg=bg_light,
        justify="left",
        anchor="w"
    )
    lbl_done_msg.pack(padx=25, pady=(0, 15), fill="x")

    chk_launch = ttk.Checkbutton(page4, text="Launch Argus PII Guard now", variable=launch_after_var)
    chk_launch.pack(padx=35, pady=10, anchor="w")

    # Bottom Navigation Frame
    footer_frame = tk.Frame(root, bg="#e2e8f0", height=50)
    footer_frame.pack(fill="x", side="bottom")

    btn_back = ttk.Button(footer_frame, text="< Back")
    btn_next = ttk.Button(footer_frame, text="Next >")
    btn_cancel = ttk.Button(footer_frame, text="Cancel", command=root.destroy)

    btn_cancel.pack(side="right", padx=(5, 20), pady=10)
    btn_next.pack(side="right", padx=5, pady=10)
    btn_back.pack(side="right", padx=5, pady=10)

    current_page_idx = 0
    page_order = ["welcome", "options", "progress", "complete"]

    def show_page(page_name):
        nonlocal current_page_idx
        current_page_idx = page_order.index(page_name)
        for p in pages.values():
            p.pack_forget()
        pages[page_name].pack(fill="both", expand=True)

        if page_name == "welcome":
            btn_back.config(state="disabled")
            btn_next.config(text="Next >", state="normal", command=on_next)
            btn_cancel.config(state="normal", text="Cancel", command=root.destroy)

        elif page_name == "options":
            btn_back.config(state="normal", command=lambda: show_page("welcome"))
            btn_next.config(text="Install >", state="normal", command=start_installation_thread)
            btn_cancel.config(state="normal", text="Cancel", command=root.destroy)

        elif page_name == "progress":
            btn_back.config(state="disabled")
            btn_next.config(state="disabled")
            btn_cancel.config(state="disabled")

        elif page_name == "complete":
            btn_back.config(state="disabled")
            btn_next.config(state="disabled")
            btn_cancel.config(state="normal", text="Finish", command=on_finish)

    def on_next():
        if action_var.get() == "uninstall":
            start_uninstallation_thread()
        else:
            show_page("options")

    def start_installation_thread():
        target_path = Path(target_path_var.get()).resolve()
        is_user = (scope_var.get() == "user")

        # Privilege Check
        priv_check = check_privileges(target_path, user_scope=is_user)
        if not priv_check["sufficient"]:
            elev_choice = messagebox.askyesno(
                "Administrative Elevation Required",
                f"Writing to '{target_path}' requires administrator privileges.\n\n"
                f"Would you like to restart setup with administrative rights (UAC)?"
            )
            if elev_choice:
                elev_args = ["--install", "--target-dir", str(target_path)]
                if is_user:
                    elev_args.append("--user-scope")
                if not add_path_var.get():
                    elev_args.append("--no-path")
                elevated = elevate_privileges(elev_args)
                if elevated:
                    root.destroy()
                    sys.exit(0)
                else:
                    messagebox.showerror("Elevation Failed", "Could not obtain administrative rights.")
            return

        show_page("progress")
        progressbar.start(10)

        def worker():
            append_log(f"Target Directory: {target_path}")
            append_log(f"Scope: {'User' if is_user else 'System'}")
            append_log("Closing any running application processes...")

            source_dir = BASE_DIR
            dist_bundle = BASE_DIR / "dist" / "Argus PII Guard"
            if dist_bundle.exists():
                source_dir = dist_bundle

            engine = InstallerEngine(source_dir=source_dir, target_dir=target_path, user_scope=is_user)
            append_log("Copying application files and frontend static assets...")
            
            res = engine.install(add_to_path=add_path_var.get())

            root.after(0, progressbar.stop)
            if res.get("success"):
                append_log("[OK] Setup operations completed successfully!")
                root.after(400, lambda: show_page("complete"))
            else:
                append_log(f"[ERROR] {res.get('message')}")
                root.after(0, lambda: messagebox.showerror("Setup Error", res.get("message")))
                root.after(0, lambda: show_page("options"))

        threading.Thread(target=worker, daemon=True).start()

    def start_uninstallation_thread():
        target_path = Path(target_path_var.get()).resolve()
        show_page("progress")
        lbl_prog_title.config(text="Uninstalling Argus PII Guard...")
        progressbar.start(10)

        def worker():
            append_log(f"Removing Argus PII Guard from {target_path}...")
            uninstaller = UninstallerEngine(install_dir=target_path)
            res = uninstaller.uninstall()

            root.after(0, progressbar.stop)
            if res.get("success"):
                append_log("[OK] Uninstallation complete.")
                lbl_done_title.config(text="Uninstallation Complete", fg=text_dark)
                lbl_done_msg.config(text="Argus PII Guard has been cleanly removed from your computer.")
                chk_launch.pack_forget()
                root.after(400, lambda: show_page("complete"))
            else:
                append_log(f"[ERROR] {res.get('error')}")
                root.after(0, lambda: messagebox.showerror("Uninstall Error", res.get("error")))

        threading.Thread(target=worker, daemon=True).start()

    def on_finish():
        if launch_after_var.get() and action_var.get() == "install":
            target_path = Path(target_path_var.get()).resolve()
            exe_names = [f"{APP_NAME}.exe", APP_NAME, "main.py"]
            target_exe = None
            for name in exe_names:
                c = target_path / name
                if c.exists():
                    target_exe = c
                    break
            if target_exe:
                try:
                    subprocess.Popen([str(target_exe)], cwd=str(target_path))
                except Exception as e:
                    print(f"Could not launch app: {e}")
        root.destroy()

    show_page("welcome")
    root.mainloop()
    return True


def main():
    parser = argparse.ArgumentParser(description="Argus PII Guard Cross-Platform Native Installer")
    parser.add_argument("--install", action="store_true", help="Perform application installation/upgrade via CLI")
    parser.add_argument("--upgrade", action="store_true", help="Upgrade an existing installation via CLI")
    parser.add_argument("--uninstall", action="store_true", help="Perform uninstallation via CLI")
    parser.add_argument("--cli", action="store_true", help="Force command-line interactive mode (bypass GUI wizard)")
    parser.add_argument("--target-dir", type=str, default=None, help="Custom installation target directory")
    parser.add_argument("--user-scope", action="store_true", help="Install into user directory (non-root)")
    parser.add_argument("--no-path", action="store_true", help="Skip modifying system PATH environment variable")
    parser.add_argument("--quiet", action="store_true", help="Non-interactive silent mode")

    args = parser.parse_args()

    # Launch GUI Setup Wizard if no explicit CLI flags are provided
    is_cli_run = args.install or args.upgrade or args.uninstall or args.quiet or args.cli or args.target_dir or args.user_scope
    if not is_cli_run:
        launched_gui = run_gui_wizard()
        if launched_gui:
            sys.exit(0)

    print("========================================================")
    print("  Argus PII Guard Native Installer & Desktop Setup")
    print("========================================================")

    target_path = Path(args.target_dir) if args.target_dir else get_default_install_path(args.user_scope)
    manifest_path = target_path / "install_manifest.json"
    is_existing = manifest_path.exists()

    # CLI Interactive mode fallback
    if not args.install and not args.upgrade and not args.uninstall:
        if args.quiet:
            args.install = True
        else:
            print(f"\nTarget path: {target_path}")
            if is_existing:
                print("An existing installation of Argus PII Guard was detected.")
                print("\nPlease select an action:")
                print("  1) Upgrade Argus PII Guard")
                print("  2) Re-install Argus PII Guard")
                print("  3) Uninstall Argus PII Guard")
                print("  4) Exit")
                choice = input("\nEnter choice [1-4]: ").strip()
                if choice in ("1", "2"):
                    args.install = True
                elif choice == "3":
                    args.uninstall = True
                else:
                    print("Exiting.")
                    sys.exit(0)
            else:
                print("\nPlease select an action:")
                print("  1) Install Argus PII Guard")
                print("  2) Uninstall Argus PII Guard")
                print("  3) Exit")
                choice = input("\nEnter choice [1-3]: ").strip()
                if choice == "1":
                    args.install = True
                elif choice == "2":
                    args.uninstall = True
                else:
                    print("Exiting.")
                    sys.exit(0)

    if args.uninstall:
        print(f"\nUninstalling Argus PII Guard from: {target_path}")
        uninstaller = UninstallerEngine(install_dir=target_path)
        res = uninstaller.uninstall()
        if res.get("success"):
            print(f"\n[OK] {res.get('message', 'Uninstallation complete.')}")
            sys.exit(0)
        else:
            print(f"\n[ERROR] Uninstallation failed: {res.get('error')}")
            sys.exit(1)

    if args.install or args.upgrade:
        print(f"\nTarget installation directory: {target_path}")
        print(f"Installation scope: {'User (Non-Root)' if args.user_scope else 'System (Admin/Root)'}")
        if is_existing:
            print("Existing installation detected. Proceeding with upgrade...")

        # Check Privileges
        priv_check = check_privileges(target_path, user_scope=args.user_scope)
        if not priv_check["sufficient"]:
            print(f"\n[!] {priv_check['message']}")
            if not args.quiet:
                elev_choice = input("Would you like to request administrative elevation? [y/N]: ").strip().lower()
                if elev_choice == "y":
                    print("Requesting elevation...")
                    elevated = elevate_privileges()
                    if elevated:
                        print("Elevated installer process launched.")
                        sys.exit(0)
                    else:
                        print("[ERROR] Elevation failed or was cancelled.")
                        sys.exit(1)
            sys.exit(1)

        source_dir = BASE_DIR
        dist_bundle = BASE_DIR / "dist" / "Argus PII Guard"
        if dist_bundle.exists():
            source_dir = dist_bundle

        installer = InstallerEngine(source_dir=source_dir, target_dir=target_path, user_scope=args.user_scope)

        print("\nDeploying application files, desktop shortcuts, and system integrations...")
        res = installer.install(add_to_path=not args.no_path)

        if res.get("success"):
            if res.get("is_upgrade"):
                print(f"\n[OK] Argus PII Guard upgrade completed successfully!")
                print(f" - Previous Version: {res.get('previous_version')}")
            else:
                print(f"\n[OK] Installation completed successfully!")
            print(f" - Install Path: {res.get('install_dir')}")
            print(f" - Shortcuts Verified: {res.get('shortcuts_created')}")
            print(f" - Manifest Updated: {res.get('manifest_path')}")
            sys.exit(0)
        else:
            print(f"\n[ERROR] Installation/Upgrade failed: {res.get('error')}")
            print(f"  Details: {res.get('message')}")
            sys.exit(1)


if __name__ == "__main__":
    main()
