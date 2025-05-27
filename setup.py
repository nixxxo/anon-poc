#!/usr/bin/env python3

import subprocess
import sys
import os


def install_dependencies():
    """Install required dependencies"""
    print("Installing dependencies...")

    # Install Python dependencies
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
    )

    print("Dependencies installed successfully!")


def check_tor():
    """Check if Tor is available on the system"""
    try:
        subprocess.run(["tor", "--version"], capture_output=True, check=True)
        print("Tor is already installed on your system.")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(
            "Tor is not installed. The application will download and run Tor automatically."
        )
        return False


def main():
    print("=== Anonymous Messenger Setup ===")

    # Install dependencies
    install_dependencies()

    # Check Tor
    check_tor()

    print("\nSetup complete!")
    print("\nUsage:")
    print("  python anon_messenger.py                    # Interactive mode")
    print("  python anon_messenger.py --server           # Start server")
    print("  python anon_messenger.py --client <string>  # Connect to server")


if __name__ == "__main__":
    main()
