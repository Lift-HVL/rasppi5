import queue
import sys
import threading
import time


class KeyboardListener:
    """Read single keypresses from the terminal in a background thread.

    Works on Linux (Raspberry Pi) via tty/termios and on Windows via msvcrt.
    Call get_key() each loop tick — returns the pressed character or None.
    """

    def __init__(self):
        self._queue: queue.Queue[str] = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            import tty
            import termios
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                while True:
                    ch = sys.stdin.read(1)
                    self._queue.put(ch)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except ImportError:
            import msvcrt
            while True:
                if msvcrt.kbhit():
                    ch = msvcrt.getch().decode('utf-8', errors='ignore')
                    self._queue.put(ch)
                time.sleep(0.05)

    def get_key(self) -> str | None:
        """Return the next queued keypress, or None if no key was pressed."""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None
