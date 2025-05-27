#!/usr/bin/env python3

import socket
import socks
import sys
import time
from rich.console import Console

console = Console()


def test_hidden_service(onion_address):
    """Test if a hidden service is reachable"""
    console.print(f"[yellow]Testing connection to: {onion_address}[/yellow]")

    # Find Tor SOCKS port
    socks_ports = [9050, 9051, 9052, 9053, 9054]
    working_port = None

    for port in socks_ports:
        try:
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.settimeout(2)
            test_sock.connect(("127.0.0.1", port))
            test_sock.close()
            working_port = port
            break
        except:
            continue

    if not working_port:
        console.print("[red]No Tor SOCKS proxy found. Please start Tor first.[/red]")
        return False

    console.print(f"[green]Using Tor SOCKS proxy on port {working_port}[/green]")

    # Configure SOCKS proxy
    socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", working_port)
    socket.socket = socks.socksocket

    # Test connection
    for attempt in range(3):
        try:
            console.print(f"[dim]Attempt {attempt + 1}: Testing connection...[/dim]")

            test_socket = socks.socksocket()
            test_socket.settimeout(30)

            start_time = time.time()
            test_socket.connect((onion_address, 8080))
            end_time = time.time()

            test_socket.close()

            console.print(
                f"[green]✅ Connection successful! ({end_time - start_time:.1f}s)[/green]"
            )
            console.print(
                "[green]The hidden service is reachable from this location.[/green]"
            )
            return True

        except socket.timeout:
            console.print(f"[yellow]Attempt {attempt + 1} timed out[/yellow]")
        except Exception as e:
            console.print(f"[red]Attempt {attempt + 1} failed: {e}[/red]")

        if attempt < 2:
            console.print("[dim]Waiting 5 seconds before retry...[/dim]")
            time.sleep(5)

    console.print("[red]❌ Hidden service is not reachable from this location.[/red]")
    console.print("[yellow]This could mean:[/yellow]")
    console.print("[yellow]- The server is not running[/yellow]")
    console.print(
        "[yellow]- The hidden service is still propagating (wait 2-3 minutes)[/yellow]"
    )
    console.print("[yellow]- Network connectivity issues[/yellow]")

    return False


def main():
    if len(sys.argv) != 2:
        console.print("[red]Usage: python test_connection.py <onion_address>[/red]")
        console.print(
            "[yellow]Example: python test_connection.py abc123.onion[/yellow]"
        )
        sys.exit(1)

    onion_address = sys.argv[1]

    # Remove .onion if not present, add if missing
    if not onion_address.endswith(".onion"):
        onion_address += ".onion"

    console.print("🧅 Hidden Service Connection Tester")
    console.print("=" * 40)

    test_hidden_service(onion_address)


if __name__ == "__main__":
    main()
