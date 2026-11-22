"""A small window that starts, resets and stops the whole demo (Postgres + Django) with buttons.

    uv run pythonw scripts/launcher.py      (start-demo.cmd does this: double-click it)
    uv run python scripts/launcher.py --selftest   (no window: start, check the login page, stop)

Opening it starts everything and opens the browser. Closing it stops everything.
Set DATABASE_URL (environment or .env) to use your own database: the local Postgres is then skipped
and "Reset demo data" is disabled, because it wipes the database.
"""

import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _pg  # noqa: E402

PORT = os.environ.get("PORT", "8000")
URL = f"http://127.0.0.1:{PORT}"
PASSWORD = os.environ.get("SEED_PASSWORD", "Demo-Pass-2026")
NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

ENV = {
    **os.environ,
    "DEBUG": os.environ.get("DEBUG", "True"),
    "SECRET_KEY": os.environ.get("SECRET_KEY", "dev-only-not-a-secret-launcher"),
    "ALLOWED_HOSTS": os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1"),
    "SEED_PASSWORD": PASSWORD,
    "PYTHONIOENCODING": "utf-8",
}
ENV_FILE = ROOT / ".env"
OWN_DB = bool(os.environ.get("DATABASE_URL")) or (
    ENV_FILE.exists() and any(line.startswith("DATABASE_URL=") for line in ENV_FILE.read_text().splitlines())
)


class Demo:
    """Everything the window does, with no GUI in it (so --selftest can drive it)."""

    def __init__(self, log):
        self.log = log
        self.server = None
        self.env = dict(ENV)

    def manage(self, *args, check=True, capture=False):
        cmd = [sys.executable, "manage.py", *args]
        proc = subprocess.run(
            cmd, cwd=ROOT, env=self.env, text=True, creationflags=NO_WINDOW,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )  # fmt: skip
        if proc.stdout.strip() and not capture:
            self.log(proc.stdout.strip())
        if check and proc.returncode:
            raise RuntimeError(f"manage.py {' '.join(args)} failed (see the log above).")
        return proc

    def start(self):
        if not OWN_DB:
            self.log("Starting the local Postgres…")
            self.env["DATABASE_URL"] = _pg.start("svkml_demo")
        self.log("Updating the database…")
        self.manage("migrate", "--noinput")
        self.manage("seed_users")
        is_empty = (
            "import sys; from apps.inventory.models import Item; sys.exit(1 if Item.objects.exists() else 0)"
        )
        empty = self.manage("shell", "-c", is_empty, check=False, capture=True)
        if empty.returncode == 0:
            self.log("Empty database: loading the demo data…")
            self.manage("seed_service_demo")
            self.manage("rebuild_stock_balances")
        self.run_server()

    def run_server(self):
        self.log("Starting the app…")
        self.server = subprocess.Popen(
            [sys.executable, "manage.py", "runserver", f"127.0.0.1:{PORT}", "--noreload"],
            cwd=ROOT, env=self.env, creationflags=NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )  # fmt: skip
        for _ in range(60):
            if self.server.poll() is not None:
                raise RuntimeError("The app stopped right after starting. Is port 8000 already in use?")
            if self.up():
                return
            time.sleep(1)
        raise RuntimeError("The app did not answer within a minute.")

    def stop_server(self):
        if self.server and self.server.poll() is None:
            self.server.terminate()
            try:
                self.server.wait(10)
            except subprocess.TimeoutExpired:
                self.server.kill()
        self.server = None

    def up(self):
        try:
            return urllib.request.urlopen(f"{URL}/login/", timeout=2).status == 200
        except OSError:
            return False

    def reset(self):
        if OWN_DB:
            raise RuntimeError("Reset is only for the local demo database, and DATABASE_URL is set.")
        self.log("Resetting: stopping the app and wiping the demo database…")
        self.stop_server()
        wipe = (
            "from django.db import connection; c = connection.cursor(); "
            "c.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public;')"
        )
        self.manage("shell", "-c", wipe)
        self.start()

    def stop(self):
        self.stop_server()
        if not OWN_DB:
            _pg.stop()


def selftest():
    demo = Demo(lambda text: print(text, flush=True))
    try:
        demo.start()
        print(f"login page up: {demo.up()}")
        return 0 if demo.up() else 1
    finally:
        demo.stop()
        print("stopped")


def gui():
    import tkinter as tk
    from tkinter import messagebox, scrolledtext

    root = tk.Tk()
    root.title("SVKML demo")
    root.geometry("640x460")
    status = tk.StringVar(value="Starting…")
    tk.Label(root, textvariable=status, font=("Segoe UI", 14, "bold"), anchor="w").pack(
        fill="x", padx=14, pady=(12, 2)
    )
    tk.Label(root, text=f"Login: admin or office    Password: {PASSWORD}", anchor="w").pack(fill="x", padx=14)
    box = scrolledtext.ScrolledText(root, height=16, state="disabled", font=("Consolas", 9))
    box.pack(fill="both", expand=True, padx=14, pady=10)
    bar = tk.Frame(root)
    bar.pack(fill="x", padx=14, pady=(0, 12))

    def log(text):
        def add():
            box.configure(state="normal")
            box.insert("end", text + "\n")
            box.see("end")
            box.configure(state="disabled")

        root.after(0, add)

    demo = Demo(log)
    buttons = {}

    def busy(on, message=None):
        if message:
            root.after(0, status.set, message)
        for button in buttons.values():
            root.after(0, lambda b=button: b.configure(state="disabled" if on else "normal"))

    def work(task, ok_message, open_browser=True):
        def run():
            busy(True)
            try:
                task()
                busy(False, ok_message)
                if open_browser:
                    webbrowser.open(URL)
            except Exception as exc:  # shown to the user, never silent
                log(f"ERROR: {exc}")
                busy(False, "Something went wrong (see the log)")

        threading.Thread(target=run, daemon=True).start()

    def reset():
        if OWN_DB:
            messagebox.showinfo("Reset", "DATABASE_URL is set, so this window won't wipe your database.")
            return
        if messagebox.askyesno(
            "Reset demo data", "This wipes the demo database and loads fresh demo data.\n\nContinue?",
            icon="warning", default="no",
        ):  # fmt: skip
            busy(True, "Resetting…")
            work(demo.reset, f"Running at {URL}")

    def quit_all():
        busy(True, "Stopping…")
        threading.Thread(target=lambda: (demo.stop(), root.after(0, root.destroy)), daemon=True).start()

    for label, command in [
        ("Open in browser", lambda: webbrowser.open(URL)),
        ("Reset demo data…", reset),
        ("Stop and quit", quit_all),
    ]:
        buttons[label] = tk.Button(bar, text=label, command=command, padx=10, pady=4)
        buttons[label].pack(side="left", padx=(0, 8))
    root.protocol("WM_DELETE_WINDOW", quit_all)
    status.set("Starting…")
    work(demo.start, f"Running at {URL}")
    root.mainloop()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    try:
        gui()
    except Exception as exc:  # pythonw has no console, so show startup errors in a box
        import tkinter.messagebox as mb

        mb.showerror("SVKML demo", str(exc))
        raise
