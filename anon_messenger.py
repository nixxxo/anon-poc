#!/usr/bin/env python3

import socket
import threading
import time
import json
import base64
import os
import sys
import argparse
import secrets
import hashlib
import hmac
import struct
from stem.control import Controller  # type: ignore
from stem import Signal
import stem.process
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.text import Text
import tempfile
import shutil
import requests
from datetime import datetime

# Memory locking support using ctypes
import ctypes
import ctypes.util
import zlib

try:
    if hasattr(ctypes, "util") and ctypes.util.find_library:
        libc_name = ctypes.util.find_library("c")
        if libc_name:
            libc = ctypes.CDLL(libc_name)
            HAS_MLOCK = True
        else:
            libc = None
            HAS_MLOCK = False
    else:
        libc = None
        HAS_MLOCK = False
except (OSError, AttributeError):
    libc = None
    HAS_MLOCK = False

# mlock constants
MCL_CURRENT = 1
MCL_FUTURE = 2

console = Console()


# Security utilities
def secure_zero_memory(data):
    """Securely zero out memory containing sensitive data"""
    if isinstance(data, str):
        data = data.encode()
    if isinstance(data, (bytes, bytearray)):
        # Overwrite memory multiple times
        for _ in range(3):
            for i in range(len(data)):
                data[i] = 0
        del data


def lock_memory(data=None):
    """Lock memory pages to prevent swapping (if available)"""
    if HAS_MLOCK and libc:
        try:
            # Call mlockall(MCL_CURRENT | MCL_FUTURE)
            result = libc.mlockall(MCL_CURRENT | MCL_FUTURE)
            if result != 0:
                # Get errno for error details
                errno_ptr = libc.__errno_location()
                errno_ptr.restype = ctypes.POINTER(ctypes.c_int)
                errno_val = errno_ptr().contents.value
                # Don't raise error, just log silently
                pass
        except:
            pass


# Security constants
MESSAGE_SIZES = [512, 1024, 2048, 4096]  # Fixed message sizes for padding
DUMMY_TRAFFIC_INTERVAL = 30  # Send dummy traffic every 30 seconds
MIN_MESSAGE_DELAY = 0.5  # Minimum delay between messages (seconds)
MAX_MESSAGE_DELAY = 3.0  # Maximum delay between messages (seconds)
CIRCUIT_REFRESH_INTERVAL = 300  # Refresh Tor circuit every 5 minutes


class TorManager:
    def __init__(self):
        self.tor_process = None
        self.controller = None
        self.socks_port = None
        self.control_port = None
        self.hidden_service_dir = None
        self.circuit_refresh_timer = None

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
            self._configure_existing_tor()
            return True

        except:
            return False

    def _configure_existing_tor(self):
        """Apply security configurations to existing Tor instance"""
        try:
            # Apply security-focused configurations
            self.controller.set_conf("NewCircuitPeriod", "30")
            self.controller.set_conf("MaxCircuitDirtiness", "600")
            self.controller.set_conf("EnforceDistinctSubnets", "1")
        except:
            pass  # Some configs might not be changeable on existing instance

    def start_tor(self):
        """Start Tor process with enhanced security configuration"""
        # First try to use existing Tor
        if self.check_existing_tor():
            self._start_circuit_refresh()
            return True

        try:
            # Find free ports
            self.socks_port = self.find_free_port(9050)
            self.control_port = self.find_free_port(self.socks_port + 1)

            # Create temporary directory for Tor data
            self.tor_data_dir = tempfile.mkdtemp(prefix="anon_msg_tor_")

            # Enhanced security configuration
            tor_config = {
                "SocksPort": str(self.socks_port),
                "ControlPort": str(self.control_port),
                "DataDirectory": self.tor_data_dir,
                "Log": ["err file /dev/null"],  # Disable all logging
                "DisableDebuggerAttachment": "0",
                "SafeLogging": "1",
                # Enhanced security settings
                "NewCircuitPeriod": "30",  # New circuit every 30 seconds
                "MaxCircuitDirtiness": "600",  # Force circuit renewal
                "EnforceDistinctSubnets": "1",  # Avoid same subnet relays
                "ClientUseIPv6": "0",  # Disable IPv6 to prevent leaks
                "StrictNodes": "1",  # Use only specified nodes
                "FascistFirewall": "1",  # Only use standard ports
                "WarnUnsafeSocks": "0",  # Disable warnings
                "AvoidDiskWrites": "1",  # Minimize disk writes
                "HardwareAccel": "1",  # Use hardware acceleration if available
            }

            # Start Tor without any output
            self.tor_process = stem.process.launch_tor_with_config(
                config=tor_config,
                init_msg_handler=lambda line: None,  # No logging
                timeout=60,
                take_ownership=True,
            )

            # Connect to controller
            self.controller = Controller.from_port(port=self.control_port)
            self.controller.authenticate()

            # Start circuit refresh timer
            self._start_circuit_refresh()

            return True

        except Exception as e:
            return False

    def _start_circuit_refresh(self):
        """Start automatic circuit refresh"""

        def refresh_circuits():
            while self.controller:
                try:
                    time.sleep(CIRCUIT_REFRESH_INTERVAL)
                    if self.controller:
                        self.controller.signal(Signal.NEWNYM)
                except:
                    break

        if self.controller:
            self.circuit_refresh_timer = threading.Thread(target=refresh_circuits)
            self.circuit_refresh_timer.daemon = True
            self.circuit_refresh_timer.start()

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

            # Wait for hidden service to propagate
            time.sleep(5)

            return onion_address

        except Exception as e:
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
            if hasattr(self, "tor_data_dir") and os.path.exists(self.tor_data_dir):
                shutil.rmtree(self.tor_data_dir)
            if self.hidden_service_dir and os.path.exists(self.hidden_service_dir):
                shutil.rmtree(self.hidden_service_dir)
        except Exception as e:
            pass  # Silent cleanup


class SecureMessenger:
    def __init__(self):
        self.key = None
        self.cipher_suite = None
        self.private_key = None
        self.public_key = None
        self.shared_secret = None
        self.message_counter = 0
        self.last_send_time = 0

        # Lock memory for sensitive data
        lock_memory(self)

    def generate_key(self):
        """Generate ECDH key pair for Perfect Forward Secrecy"""
        self.private_key = ec.generate_private_key(ec.SECP384R1(), default_backend())
        self.public_key = self.private_key.public_key()

        # Also generate a fallback Fernet key for compatibility
        self.key = Fernet.generate_key()
        self.cipher_suite = Fernet(self.key)

        # Create compact connection string
        # Use raw public key bytes instead of PEM (much shorter)
        public_numbers = self.public_key.public_numbers()

        # Encode public key as compact binary (48 bytes for P-384)
        x_bytes = public_numbers.x.to_bytes(48, byteorder="big")
        y_bytes = public_numbers.y.to_bytes(48, byteorder="big")
        public_raw = x_bytes + y_bytes  # 96 bytes total

        # Combine with Fernet key (32 bytes)
        combined_data = public_raw + self.key  # 128 bytes total

        # Compress and encode with base32 for better readability
        compressed = zlib.compress(combined_data, level=9)
        connection_string = base64.b32encode(compressed).decode().rstrip("=")

        return connection_string

    def set_key(self, key_str):
        """Set encryption key from connection string"""
        try:
            key_str = key_str.strip()

            # Try new compact format first
            try:
                # Add padding if needed for base32
                key_str_padded = key_str + "=" * (8 - len(key_str) % 8) % 8
                compressed = base64.b32decode(key_str_padded.encode())
                decoded = zlib.decompress(compressed)

                if len(decoded) == 128:  # 96 bytes public key + 32 bytes Fernet key
                    # Extract public key coordinates
                    public_raw = decoded[:96]
                    fernet_key = decoded[96:]

                    x_bytes = public_raw[:48]
                    y_bytes = public_raw[48:96]

                    # Reconstruct public key
                    x = int.from_bytes(x_bytes, byteorder="big")
                    y = int.from_bytes(y_bytes, byteorder="big")

                    public_numbers = ec.EllipticCurvePublicNumbers(x, y, ec.SECP384R1())
                    server_public_key = public_numbers.public_key(default_backend())

                    # Generate our own key pair
                    self.private_key = ec.generate_private_key(
                        ec.SECP384R1(), default_backend()
                    )
                    self.public_key = self.private_key.public_key()

                    # Perform ECDH
                    self.shared_secret = self.private_key.exchange(
                        ec.ECDH(), server_public_key
                    )

                    # Fallback to Fernet for compatibility
                    self.key = fernet_key
                    self.cipher_suite = Fernet(self.key)

                    return True
            except:
                pass  # Fall through to legacy format

            # Try legacy format
            try:
                decoded = base64.urlsafe_b64decode(key_str.encode())

                if b"||" in decoded:
                    # Old PEM format with ECDH public key
                    public_bytes, fernet_key = decoded.split(b"||", 1)

                    # Load the server's public key
                    server_public_key = serialization.load_pem_public_key(
                        public_bytes, backend=default_backend()
                    )

                    # Generate our own key pair
                    self.private_key = ec.generate_private_key(
                        ec.SECP384R1(), default_backend()
                    )
                    self.public_key = self.private_key.public_key()

                    # Perform ECDH
                    self.shared_secret = self.private_key.exchange(
                        ec.ECDH(), server_public_key
                    )

                    # Fallback to Fernet for compatibility
                    self.key = fernet_key
                    self.cipher_suite = Fernet(self.key)

                else:
                    # Legacy format - just Fernet key
                    self.key = decoded
                    self.cipher_suite = Fernet(self.key)

                return True
            except:
                pass

            return False
        except Exception as e:
            return False

    def _derive_message_key(self, message_id):
        """Derive unique key for each message using HKDF"""
        if self.shared_secret:
            # Use ECDH shared secret with message counter
            hkdf = HKDF(
                algorithm=hashes.SHA256(),
                length=32,
                salt=None,
                info=f"msg_{message_id}".encode(),
                backend=default_backend(),
            )
            return hkdf.derive(self.shared_secret + struct.pack(">Q", message_id))
        return None

    def _pad_message(self, message):
        """Pad message to fixed size for traffic analysis protection"""
        # Convert to bytes
        if isinstance(message, str):
            message_bytes = message.encode("utf-8")
        else:
            message_bytes = message

        # Add random padding
        padding_size = secrets.randbelow(64) + 16  # 16-80 random bytes
        padding = secrets.token_bytes(padding_size)

        # Choose target size
        current_size = len(message_bytes) + len(padding) + 4  # +4 for length prefix
        target_size = next(size for size in MESSAGE_SIZES if size >= current_size)

        # Add padding to reach target size
        total_padding_needed = target_size - len(message_bytes) - 4
        if total_padding_needed > len(padding):
            padding += secrets.token_bytes(total_padding_needed - len(padding))
        else:
            padding = padding[:total_padding_needed]

        # Format: [message_length(4)] + [message] + [padding]
        return struct.pack(">I", len(message_bytes)) + message_bytes + padding

    def _unpad_message(self, padded_data):
        """Remove padding from message"""
        if len(padded_data) < 4:
            return None

        message_length = struct.unpack(">I", padded_data[:4])[0]
        if message_length > len(padded_data) - 4:
            return None

        return padded_data[4 : 4 + message_length]

    def _apply_timing_obfuscation(self):
        """Apply random delay for timing attack protection"""
        current_time = time.time()
        time_since_last = current_time - self.last_send_time

        # Add random delay between MIN and MAX
        delay = (
            secrets.randbelow(int((MAX_MESSAGE_DELAY - MIN_MESSAGE_DELAY) * 1000))
            / 1000.0
        )
        delay += MIN_MESSAGE_DELAY

        # If we sent recently, add extra delay
        if time_since_last < MIN_MESSAGE_DELAY:
            delay += MIN_MESSAGE_DELAY - time_since_last

        time.sleep(delay)
        self.last_send_time = time.time()

    def encrypt_message(self, message):
        """Encrypt a message with PFS and traffic analysis protection"""
        if not self.cipher_suite:
            return None

        try:
            # Apply timing obfuscation
            self._apply_timing_obfuscation()

            # Pad message
            padded_message = self._pad_message(message)

            # Increment message counter for PFS
            self.message_counter += 1

            # Try to use ECDH-derived key first
            message_key = self._derive_message_key(self.message_counter)
            if message_key:
                # Use AES-GCM with derived key
                iv = secrets.token_bytes(12)  # 96-bit IV for GCM
                cipher = Cipher(
                    algorithms.AES(message_key),
                    modes.GCM(iv),
                    backend=default_backend(),
                )
                encryptor = cipher.encryptor()
                ciphertext = encryptor.update(padded_message) + encryptor.finalize()

                # Format: [counter(8)] + [iv(12)] + [tag(16)] + [ciphertext]
                encrypted_data = (
                    struct.pack(">Q", self.message_counter)
                    + iv
                    + encryptor.tag
                    + ciphertext
                )
                return base64.urlsafe_b64encode(encrypted_data).decode()
            else:
                # Fallback to Fernet
                return self.cipher_suite.encrypt(padded_message).decode()

        except Exception as e:
            return None

    def decrypt_message(self, encrypted_message):
        """Decrypt a message"""
        if not self.cipher_suite:
            return None

        try:
            encrypted_data = base64.urlsafe_b64decode(encrypted_message.encode())

            # Check if it's ECDH format (has counter prefix)
            if len(encrypted_data) >= 36:  # 8+12+16 minimum
                counter = struct.unpack(">Q", encrypted_data[:8])[0]
                iv = encrypted_data[8:20]
                tag = encrypted_data[20:36]
                ciphertext = encrypted_data[36:]

                # Try to derive the key
                message_key = self._derive_message_key(counter)
                if message_key:
                    try:
                        cipher = Cipher(
                            algorithms.AES(message_key),
                            modes.GCM(iv, tag),
                            backend=default_backend(),
                        )
                        decryptor = cipher.decryptor()
                        padded_message = (
                            decryptor.update(ciphertext) + decryptor.finalize()
                        )

                        # Unpad the message
                        message_bytes = self._unpad_message(padded_message)
                        if message_bytes:
                            return message_bytes.decode("utf-8")
                    except:
                        pass  # Fall through to Fernet

            # Fallback to Fernet decryption
            padded_message = self.cipher_suite.decrypt(encrypted_data)
            message_bytes = self._unpad_message(padded_message)
            if message_bytes:
                return message_bytes.decode("utf-8")
            else:
                # Legacy format without padding
                return padded_message.decode("utf-8")

        except:
            return None

    def generate_dummy_message(self):
        """Generate dummy traffic for traffic analysis protection"""
        dummy_content = secrets.token_hex(secrets.randbelow(100) + 50)
        return self.encrypt_message(f"DUMMY:{dummy_content}")

    def is_dummy_message(self, decrypted_message):
        """Check if message is dummy traffic"""
        return decrypted_message and decrypted_message.startswith("DUMMY:")

    def cleanup(self):
        """Securely clean up sensitive data"""
        if self.key:
            secure_zero_memory(self.key)
        if self.shared_secret:
            secure_zero_memory(self.shared_secret)
        self.private_key = None
        self.public_key = None
        self.cipher_suite = None


class AnonymousServer:
    def __init__(self, port=8080):
        self.port = port
        self.socket = None
        self.clients = []
        self.running = False
        self.tor_manager = TorManager()
        self.messenger = SecureMessenger()
        self.dummy_traffic_timer = None

    def start(self):
        """Start the anonymous server"""
        console.print("[yellow]Starting Tor...[/yellow]")

        # Start Tor
        if not self.tor_manager.start_tor():
            console.print("[red]Failed to start Tor[/red]")
            return False

        console.print("[yellow]Creating hidden service...[/yellow]")

        # Create socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.socket.bind(("127.0.0.1", self.port))
            self.socket.listen(5)

            # Create hidden service
            onion_address = self.tor_manager.create_hidden_service(self.port)
            if not onion_address:
                console.print("[red]Failed to create hidden service[/red]")
                return False

            # Generate encryption key
            encryption_key = self.messenger.generate_key()

            # Display connection info
            connection_string = f"{onion_address}:{encryption_key}"

            console.print(
                Panel.fit(
                    f"[bold green]Server Started[/bold green]\n\n"
                    f"[yellow]Connection String:[/yellow]\n"
                    f"[bold cyan]{connection_string}[/bold cyan]\n\n"
                    f"[dim]Share this with others to connect securely[/dim]",
                    title="Ready",
                    width=80,
                )
            )

            self.running = True

            # Start dummy traffic generation
            self._start_dummy_traffic()

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

    def _start_dummy_traffic(self):
        """Start dummy traffic generation to obscure real traffic patterns"""

        def generate_dummy_traffic():
            while self.running:
                try:
                    time.sleep(
                        DUMMY_TRAFFIC_INTERVAL + secrets.randbelow(30)
                    )  # 30-60s intervals
                    if self.running and len(self.clients) > 0:
                        dummy_msg = self.messenger.generate_dummy_message()
                        if dummy_msg:
                            # Send to all clients
                            for client in self.clients[
                                :
                            ]:  # Copy list to avoid modification during iteration
                                try:
                                    client.send(dummy_msg.encode())
                                except:
                                    # Remove failed client
                                    if client in self.clients:
                                        self.clients.remove(client)
                                        client.close()
                except:
                    break

        if self.running:
            self.dummy_traffic_timer = threading.Thread(target=generate_dummy_traffic)
            self.dummy_traffic_timer.daemon = True
            self.dummy_traffic_timer.start()

    def handle_client(self, client_socket):
        """Handle individual client connection"""
        self.clients.append(client_socket)

        try:
            while self.running:
                data = client_socket.recv(1024)
                if not data:
                    break

                # Forward encrypted message to all other clients
                # No need to decrypt since all clients share the same key
                for client in self.clients:
                    if client != client_socket:
                        try:
                            client.send(data)
                        except:
                            # Remove failed client
                            if client in self.clients:
                                self.clients.remove(client)
                                client.close()

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
        self.messenger.cleanup()
        self.tor_manager.cleanup()


class AnonymousClient:
    def __init__(self):
        self.socket = None
        self.connected = False
        self.messenger = SecureMessenger()
        self.socks_port = 9050

    def connect(self, connection_string):
        """Connect to server using connection string"""
        try:
            # Parse connection string
            connection_string = connection_string.strip()
            parts = connection_string.split(":")
            if len(parts) != 2:
                return False

            onion_address = parts[0].strip()
            encryption_key = parts[1].strip()

            # Set encryption key
            if not self.messenger.set_key(encryption_key):
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
                    # Test the SOCKS proxy by connecting to it
                    test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    test_sock.settimeout(2)
                    test_sock.connect(("127.0.0.1", port))
                    test_sock.close()
                    working_port = port
                    break
                except:
                    continue

            if not working_port:
                return False

            self.socks_port = working_port
            socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", self.socks_port)
            socket.socket = socks.socksocket

            # Connect to hidden service with multiple retries
            max_retries = 3
            retry_delay = 10

            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        time.sleep(retry_delay)

                    self.socket = socks.socksocket()
                    self.socket.settimeout(45)
                    self.socket.connect((onion_address, 8080))
                    break

                except socket.timeout:
                    if self.socket:
                        self.socket.close()
                    if attempt == max_retries - 1:
                        return False
                except Exception as conn_err:
                    if self.socket:
                        self.socket.close()
                    if attempt == max_retries - 1:
                        return False

            self.connected = True

            # Start receiving messages
            receive_thread = threading.Thread(target=self.receive_messages)
            receive_thread.daemon = True
            receive_thread.start()

            return True

        except Exception as e:
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

                if decrypted_msg and not self.messenger.is_dummy_message(decrypted_msg):
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    console.print(
                        f"[dim]{timestamp}[/dim] [blue]>[/blue] {decrypted_msg}"
                    )

            except Exception as e:
                # Only break on socket errors, not decryption errors
                if self.connected:
                    continue
                break

    def send_message(self, message):
        """Send encrypted message"""
        if not self.connected:
            return False

        try:
            encrypted_msg = self.messenger.encrypt_message(message)
            if encrypted_msg:
                self.socket.send(encrypted_msg.encode())
                timestamp = datetime.now().strftime("%H:%M:%S")
                console.print(f"[dim]{timestamp}[/dim] [cyan]You:[/cyan] {message}")
                return True
        except Exception as e:
            # Connection lost
            self.connected = False
            console.print(f"[red]Connection lost[/red]")

        return False

    def input_handler(self):
        """Handle user input in a separate thread"""
        while self.connected:
            try:
                message = input()
                if message.lower().strip() in ["quit", "exit", "/quit", "/exit"]:
                    self.connected = False
                    break

                if message.strip():
                    if not self.send_message(message):
                        # Failed to send, connection might be lost
                        break
            except (KeyboardInterrupt, EOFError):
                self.connected = False
                break

    def start_chat_ui(self):
        """Start the interactive chat UI"""
        # Clear screen and show header
        console.clear()
        console.print(
            Panel.fit(
                "[bold green]Anonymous Chat Connected[/bold green]\n"
                "[dim]Type messages and press Enter. Type 'quit' to exit.[/dim]",
                title="Secure Chat",
            )
        )

        # Start input handler thread
        input_thread = threading.Thread(target=self.input_handler)
        input_thread.daemon = True
        input_thread.start()

        try:
            while self.connected:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.connected = False

    def disconnect(self):
        """Disconnect from server"""
        self.connected = False
        if self.socket:
            self.socket.close()
        self.messenger.cleanup()


def main():
    parser = argparse.ArgumentParser(description="Anonymous Terminal Messenger")
    parser.add_argument("--server", action="store_true", help="Start as server")
    parser.add_argument(
        "--client", type=str, help="Connect as client with connection string"
    )

    args = parser.parse_args()

    if args.server:
        # Server mode
        server = AnonymousServer()
        try:
            if server.start():
                while True:
                    time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            server.stop()

    elif args.client:
        # Client mode
        client = AnonymousClient()
        if client.connect(args.client):
            client.start_chat_ui()
        client.disconnect()

    else:
        # Interactive mode
        console.print(
            Panel.fit(
                "[bold]Anonymous Terminal Messenger[/bold]\n"
                "[dim]Secure messaging through Tor[/dim]",
                title="AnonMsg",
            )
        )

        console.print("\n[yellow]Choose mode:[/yellow]")
        console.print("1. Start Server")
        console.print("2. Connect to Server")

        choice = Prompt.ask("Select", choices=["1", "2"])

        if choice == "1":
            # Start server
            server = AnonymousServer()
            try:
                if server.start():
                    console.print("\n[yellow]Press Ctrl+C to stop[/yellow]")
                    while True:
                        time.sleep(1)
            except KeyboardInterrupt:
                pass
            finally:
                server.stop()

        else:
            # Connect as client
            connection_string = Prompt.ask("[yellow]Enter connection string[/yellow]")
            client = AnonymousClient()
            if client.connect(connection_string):
                client.start_chat_ui()
            client.disconnect()


if __name__ == "__main__":
    main()
