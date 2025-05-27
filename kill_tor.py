#!/usr/bin/env python3

import subprocess
import sys
import os
import signal


def kill_tor_processes():
    """Kill existing Tor processes that might be causing conflicts"""
    try:
        if sys.platform == "darwin" or sys.platform == "linux":
            # macOS and Linux
            result = subprocess.run(["pgrep", "tor"], capture_output=True, text=True)
            if result.returncode == 0:
                pids = result.stdout.strip().split("\n")
                for pid in pids:
                    if pid:
                        try:
                            os.kill(int(pid), signal.SIGTERM)
                            print(f"Killed Tor process {pid}")
                        except:
                            pass
            else:
                print("No Tor processes found")
        else:
            # Windows
            subprocess.run(["taskkill", "/F", "/IM", "tor.exe"], capture_output=True)
            print("Attempted to kill Tor processes on Windows")
    except Exception as e:
        print(f"Error killing Tor processes: {e}")


def main():
    print("🔄 Killing existing Tor processes...")
    kill_tor_processes()
    print("✅ Done! You can now start the anonymous messenger.")


if __name__ == "__main__":
    main()
