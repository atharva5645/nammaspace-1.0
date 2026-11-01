"""Pause or resume a running gsplat training (Windows), without losing progress.

gsplat only saves at the end of training, so stopping it loses everything. This freezes
the training processes instead; they keep their GPU memory and continue exactly where
they stopped. Survives sleep/hibernate, but NOT a shutdown or restart.

  python pipeline/tools/pause_training.py pause
  python pipeline/tools/pause_training.py resume
  python pipeline/tools/pause_training.py status
"""
import ctypes
import subprocess
import sys

PROCESS_SUSPEND_RESUME = 0x0800
ntdll = ctypes.WinDLL("ntdll")
kernel32 = ctypes.WinDLL("kernel32")


def training_pids() -> list[int]:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | "
         "Where-Object { $_.CommandLine -match 'simple_trainer|gsplat_train' } | "
         "ForEach-Object { $_.ProcessId }"],
        capture_output=True, text=True).stdout
    return [int(x) for x in out.split()]


def apply(pid: int, fn) -> bool:
    handle = kernel32.OpenProcess(PROCESS_SUSPEND_RESUME, False, pid)
    if not handle:
        return False
    try:
        return fn(handle) == 0
    finally:
        kernel32.CloseHandle(handle)


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    pids = training_pids()
    if not pids:
        sys.exit("No gsplat training is running (a restart or shutdown ends it).")
    if action == "status":
        print(f"training processes: {pids}")
        return
    fn = {"pause": ntdll.NtSuspendProcess, "resume": ntdll.NtResumeProcess}[action]
    for pid in pids:
        print(f"{action} {pid}: {'ok' if apply(pid, fn) else 'FAILED'}")


if __name__ == "__main__":
    main()
