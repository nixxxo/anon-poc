#!/usr/bin/env python3

import socket
import threading
import time
import json
import base64
import os
import sys
import argparse
from stem.control import Controller
from stem import Signal
import stem.process
from cryptography.fernet import Fernet
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.text import Text
import tempfile
import shutil
import requests

console = Console()


class TorManager:
    def __init__(self):
        self.tor_process = None
        self.controller = None
        self.socks_port = None
        self.control_port = None
        self.hidden_service_dir = None

    def find_free_port(self, start_port=9050):
        """Find a free port starting from start_port"""
        import socket

        for port in range(start_port, start_port + 100):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("127.0.0.1", port))
                    return port
            except OSError:
                continue
        raise Exception("No free ports available")

    def check_existing_tor(self):
        """Check if Tor is already running and try to use it"""
        try:
            # Try to connect to default Tor control port
            controller = Controller.from_port(port=9051)
            controller.authenticate()

            # Check if SOCKS is available
            import socks

            socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 9050)
            test_socket = socks.socksocket()
            test_socket.settimeout(5)

            # If we get here, existing Tor is working
            self.controller = controller
            self.socks_port = 9050
            self.control_port = 9051
            console.print("[green]Using existing Tor instance![/green]")
            return True

        except:
            return False

    def start_tor(self):
        """Start Tor process with minimal configuration"""
        # First try to use existing Tor
        if self.check_existing_tor():
            return True

        try:
            # Find free ports
            self.socks_port = self.find_free_port(9050)
            self.control_port = self.find_free_port(self.socks_port + 1)

            console.print(
                f"[yellow]Starting Tor on ports {self.socks_port}/{self.control_port}...[/yellow]"
            )

            # Create temporary directory for Tor data
            self.tor_data_dir = tempfile.mkdtemp(prefix="anon_msg_tor_")

            tor_config = {
                "SocksPort": str(self.socks_port),
                "ControlPort": str(self.control_port),
                "DataDirectory": self.tor_data_dir,
                "Log": ["warn stdout"],
                "DisableDebuggerAttachment": "0",
            }

            self.tor_process = stem.process.launch_tor_with_config(
                config=tor_config,
                init_msg_handler=lambda line: (
                    console.print(f"[dim]{line}[/dim]")
                    if "Bootstrapped 100%" in line
                    else None
                ),
            )

            # Connect to controller
            self.controller = Controller.from_port(port=self.control_port)
            self.controller.authenticate()

            console.print("[green]Tor started successfully![/green]")
            return True

        except Exception as e:
            console.print(f"[red]Failed to start Tor: {e}[/red]")
            console.print(
                "[yellow]Try stopping any existing Tor processes or restart your system[/yellow]"
            )
            return False

    def create_hidden_service(self, port):
        """Create a hidden service for the given port"""
        try:
            # Create temporary hidden service directory
            self.hidden_service_dir = tempfile.mkdtemp(prefix="anon_msg_hs_")

            result = self.controller.create_hidden_service(
                self.hidden_service_dir, port, target_port=port
            )

            # Handle different stem API versions
            if hasattr(result, "service_id"):
                onion_address = result.service_id + ".onion"
            elif hasattr(result, "hostname"):
                onion_address = result.hostname
            else:
                # Fallback: read from hostname file
                hostname_file = os.path.join(self.hidden_service_dir, "hostname")
                if os.path.exists(hostname_file):
                    with open(hostname_file, "r") as f:
                        onion_address = f.read().strip()
                else:
                    raise Exception("Could not determine onion address")

            console.print(f"[green]Hidden service created: {onion_address}[/green]")
            return onion_address

        except Exception as e:
            console.print(f"[red]Failed to create hidden service: {e}[/red]")
            return None

    def cleanup(self):
        """Clean up Tor process and temporary directories"""
        try:
            if self.controller:
                # Only close if we started our own Tor process
                if self.tor_process:
                    self.controller.close()
                else:
                    # We used existing Tor, just disconnect
                    self.controller.close()
            if self.tor_process:
                self.tor_process.kill()
                console.print("[yellow]Stopped Tor process[/yellow]")
            if hasattr(self, "tor_data_dir") and os.path.exists(self.tor_data_dir):
                shutil.rmtree(self.tor_data_dir)
            if self.hidden_service_dir and os.path.exists(self.hidden_service_dir):
                shutil.rmtree(self.hidden_service_dir)
        except Exception as e:
            console.print(f"[yellow]Cleanup warning: {e}[/yellow]")


class SecureMessenger:
    def __init__(self):
        self.key = None
        self.cipher_suite = None

    def generate_key(self):
        """Generate a new encryption key"""
        self.key = Fernet.generate_key()
        self.cipher_suite = Fernet(self.key)
        return base64.urlsafe_b64encode(self.key).decode()

    def set_key(self, key_str):
        """Set encryption key from string"""
        try:
            # Clean the key string
            key_str = key_str.strip()
            self.key = base64.urlsafe_b64decode(key_str.encode())
            self.cipher_suite = Fernet(self.key)
            return True
        except Exception as e:
            console.print(f"[red]Key validation error: {e}[/red]")
            console.print(f"[yellow]Key length: {len(key_str)}, Expected: ~44 characters[/yellow]")
            return False

    def encrypt_message(self, message):
        """Encrypt a message"""
        if not self.cipher_suite:
            return None
        return self.cipher_suite.encrypt(message.encode()).decode()

    def decrypt_message(self, encrypted_message):
        """Decrypt a message"""
        if not self.cipher_suite:
            return None
        try:
            return self.cipher_suite.decrypt(encrypted_message.encode()).decode()
        except:
            return None


class AnonymousServer:
    def __init__(self, port=8080):
        self.port = port
        self.socket = None
        self.clients = []
        self.running = False
        self.tor_manager = TorManager()
        self.messenger = SecureMessenger()

    def start(self):
        """Start the anonymous server"""
        # Start Tor
        if not self.tor_manager.start_tor():
            return False

        # Create socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.socket.bind(("127.0.0.1", self.port))
            self.socket.listen(5)

            # Create hidden service
            onion_address = self.tor_manager.create_hidden_service(self.port)
            if not onion_address:
                return False

            # Generate encryption key
            encryption_key = self.messenger.generate_key()

            # Display connection info
            connection_string = f"{onion_address}:{encryption_key}"

            console.print(
                Panel.fit(
                    f"[bold green]Anonymous Message Server Started![/bold green]\n\n"
                    f"[yellow]Connection String:[/yellow]\n"
                    f"[bold cyan]{connection_string}[/bold cyan]\n\n"
                    f"[dim]Share this string with others to connect anonymously.\n"
                    f"Server is running on port {self.port}[/dim]",
                    title="Server Ready",
                    width=120,
                )
            )

            # Also print it separately for easy copying
            console.print(f"\n[yellow]Connection String (copy this):[/yellow]")
            console.print(f"[bold green]{connection_string}[/bold green]")

            self.running = True

            # Accept connections
            while self.running:
                try:
                    client_socket, addr = self.socket.accept()
                    client_thread = threading.Thread(
                        target=self.handle_client, args=(client_socket,)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                except:
                    break

        except Exception as e:
            console.print(f"[red]Server error: {e}[/red]")
            return False

        return True

    def handle_client(self, client_socket):
        """Handle individual client connection"""
        self.clients.append(client_socket)

        try:
            while self.running:
                data = client_socket.recv(1024)
                if not data:
                    break

                # Decrypt and broadcast message
                encrypted_msg = data.decode()
                decrypted_msg = self.messenger.decrypt_message(encrypted_msg)

                if decrypted_msg:
                    # Re-encrypt and send to all other clients
                    for client in self.clients:
                        if client != client_socket:
                            try:
                                client.send(data)
                            except:
                                pass

        except Exception as e:
            pass
        finally:
            if client_socket in self.clients:
                self.clients.remove(client_socket)
            client_socket.close()

    def stop(self):
        """Stop the server"""
        self.running = False
        if self.socket:
            self.socket.close()
        for client in self.clients:
            client.close()
        self.tor_manager.cleanup()


class AnonymousClient:
    def __init__(self):
        self.socket = None
        self.connected = False
        self.messenger = SecureMessenger()
        self.socks_port = 9050  # Default, will be updated if needed

    def connect(self, connection_string):
        """Connect to server using connection string"""
        try:
            # Parse connection string
            connection_string = connection_string.strip()
            parts = connection_string.split(":")
            if len(parts) != 2:
                console.print("[red]Invalid connection string format[/red]")
                console.print(f"[yellow]Expected format: onion_address:encryption_key[/yellow]")
                console.print(f"[yellow]Found {len(parts)} parts: {parts}[/yellow]")
                return False

            onion_address = parts[0].strip()
            encryption_key = parts[1].strip()
            
            console.print(f"[yellow]Onion address: {onion_address}[/yellow]")
            console.print(f"[yellow]Key length: {len(encryption_key)}[/yellow]")

            # Set encryption key
            if not self.messenger.set_key(encryption_key):
                console.print("[red]Invalid encryption key[/red]")
                return False

            # Create socket with SOCKS proxy
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(30)

            # Check for existing Tor or find the right SOCKS port
            import socks

            # Try to find working SOCKS port
            socks_ports = [9050, 9051, 9052, 9053, 9054]
            working_port = None

            for port in socks_ports:
                try:
                    socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", port)
                    test_socket = socks.socksocket()
                    test_socket.settimeout(5)
                    # If this doesn't throw an exception, the port works
                    working_port = port
                    break
                except:
                    continue

            if not working_port:
                console.print(
                    "[red]No Tor SOCKS proxy found. Make sure Tor is running.[/red]"
                )
                return False

            self.socks_port = working_port
            socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", self.socks_port)
            socket.socket = socks.socksocket

            console.print(
                f"[yellow]Connecting through Tor (port {self.socks_port})...[/yellow]"
            )

            # Connect to hidden service
            self.socket = socks.socksocket()
            self.socket.connect((onion_address, 8080))

            self.connected = True
            console.print("[green]Connected anonymously![/green]")

            # Start receiving messages
            receive_thread = threading.Thread(target=self.receive_messages)
            receive_thread.daemon = True
            receive_thread.start()

            return True

        except Exception as e:
            console.print(f"[red]Connection failed: {e}[/red]")
            return False

    def receive_messages(self):
        """Receive and display messages"""
        while self.connected:
            try:
                data = self.socket.recv(1024)
                if not data:
                    break

                encrypted_msg = data.decode()
                decrypted_msg = self.messenger.decrypt_message(encrypted_msg)

                if decrypted_msg:
                    console.print(f"[blue]> {decrypted_msg}[/blue]")

            except:
                break

    def send_message(self, message):
        """Send encrypted message"""
        if not self.connected:
            return False

        try:
            encrypted_msg = self.messenger.encrypt_message(message)
            if encrypted_msg:
                self.socket.send(encrypted_msg.encode())
                return True
        except:
            pass

        return False

    def disconnect(self):
        """Disconnect from server"""
        self.connected = False
        if self.socket:
            self.socket.close()


def main():
    parser = argparse.ArgumentParser(description="Anonymous Terminal Messenger")
    parser.add_argument("--server", action="store_true", help="Start as server")
    parser.add_argument(
        "--client", type=str, help="Connect as client with connection string"
    )

    args = parser.parse_args()

    console.print(
        Panel.fit(
            "[bold]Anonymous Terminal Messenger[/bold]\n"
            "[dim]Fully anonymous messaging through Tor[/dim]",
            title="AnonMsg",
        )
    )

    if args.server:
        # Server mode
        server = AnonymousServer()
        try:
            if server.start():
                console.print("\n[yellow]Press Ctrl+C to stop server[/yellow]")
                while True:
                    time.sleep(1)
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down server...[/yellow]")
        finally:
            server.stop()

    elif args.client:
        # Client mode
        client = AnonymousClient()

        if client.connect(args.client):
            console.print(
                "\n[green]You can now send messages. Type 'quit' to exit.[/green]"
            )

            try:
                while True:
                    message = Prompt.ask("[bold]Message")
                    if message.lower() == "quit":
                        break

                    if not client.send_message(message):
                        console.print("[red]Failed to send message[/red]")
                        break

            except KeyboardInterrupt:
                pass
            finally:
                client.disconnect()

    else:
        # Interactive mode
        console.print("\n[yellow]Choose mode:[/yellow]")
        console.print("1. Start Server (others connect to you)")
        console.print("2. Connect to Server")

        choice = Prompt.ask("Select", choices=["1", "2"])

        if choice == "1":
            # Start server
            server = AnonymousServer()
            try:
                if server.start():
                    console.print("\n[yellow]Press Ctrl+C to stop server[/yellow]")
                    while True:
                        time.sleep(1)
            except KeyboardInterrupt:
                console.print("\n[yellow]Shutting down server...[/yellow]")
            finally:
                server.stop()

        else:
            # Connect as client
            connection_string = Prompt.ask("[yellow]Enter connection string[/yellow]")

            client = AnonymousClient()

            if client.connect(connection_string):
                console.print(
                    "\n[green]You can now send messages. Type 'quit' to exit.[/green]"
                )

                try:
                    while True:
                        message = Prompt.ask("[bold]Message")
                        if message.lower() == "quit":
                            break

                        if not client.send_message(message):
                            console.print("[red]Failed to send message[/red]")
                            break

                except KeyboardInterrupt:
                    pass
                finally:
                    client.disconnect()


if __name__ == "__main__":
    main()
