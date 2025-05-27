# Anonymous Terminal Messenger

A minimal PoC of a fully anonymous terminal interactive messaging app with Tor routing, designed for zero metadata leakage and maximum anonymity.

## 🔒 Security Features

-   **Full Tor Integration**: All traffic routed through Tor hidden services
-   **End-to-End Encryption**: Messages encrypted with Fernet (AES 128)
-   **Zero Logging**: No data persistence or logging
-   **Ephemeral Keys**: Encryption keys generated per session
-   **No Metadata Leakage**: No IP addresses, timestamps, or user data stored
-   **Automatic Tor Setup**: No manual Tor configuration required

## 🚀 Quick Start

### 1. Setup

```bash
python setup.py
```

### 2. Start Server (Host)

```bash
python anon_messenger.py --server
```

This will:

-   Start Tor automatically
-   Create a hidden service
-   Generate an encryption key
-   Display a connection string like: `abc123def456.onion:gAAAAABh...`

### 3. Connect as Client

```bash
python anon_messenger.py --client "abc123def456.onion:gAAAAABh..."
```

### 4. Interactive Mode

```bash
python anon_messenger.py
```

Choose server or client mode interactively.

## 🌐 Connection Options

### Same Machine

-   Server and client on same computer
-   Uses localhost connection through Tor

### Same WiFi Network

-   Each person runs the client with the connection string
-   Traffic routed through Tor for anonymity

### Different WiFi Networks

-   Fully anonymous communication through Tor network
-   No direct connection between networks

## 📡 How It Works

1. **Server Mode**:

    - Launches embedded Tor process
    - Creates hidden service (.onion address)
    - Generates unique encryption key
    - Shares connection string

2. **Client Mode**:

    - Connects through Tor SOCKS proxy
    - Uses shared encryption key
    - All messages encrypted end-to-end

3. **Message Flow**:
    - Client encrypts message with shared key
    - Sends through Tor to hidden service
    - Server relays to all connected clients
    - Clients decrypt and display

## 🛡️ Security Design

### Anonymous Communication

-   No IP addresses logged or visible
-   All traffic through Tor hidden services
-   Multiple layers of encryption (Tor + message encryption)

### Data Protection

-   No persistent storage
-   Temporary directories cleaned on exit
-   Encryption keys generated per session
-   No user identification required

### Metadata Protection

-   No timestamps stored
-   No connection logs
-   No user tracking
-   Ephemeral Tor configuration

## ⚠️ Security Considerations

This is a **Proof of Concept** for educational purposes. For production use:

1. **Key Exchange**: Implement secure key exchange protocol
2. **Forward Secrecy**: Add perfect forward secrecy
3. **Authentication**: Add user authentication if needed
4. **Auditing**: Security audit the codebase
5. **Updates**: Keep dependencies updated

## 🔧 Requirements

-   Python 3.7+
-   Internet connection for Tor
-   ~50MB disk space for Tor

## 🏗️ Architecture

```
Client ←→ Tor Network ←→ Hidden Service ←→ Server
   ↑                                        ↑
[Encrypted Messages]              [Message Relay]
```

## 📝 Usage Examples

### Host a private chat room:

```bash
python anon_messenger.py --server
# Share the connection string with participants
```

### Join a chat room:

```bash
python anon_messenger.py --client "onion_address:encryption_key"
```

### Group messaging:

-   One person runs server
-   Multiple people connect as clients
-   All messages are relayed to all participants

## 🚨 Limitations

-   **Single Server**: One person must host
-   **Session-based**: No persistent chat history
-   **Text Only**: No file sharing
-   **Basic UI**: Terminal-based interface

## 🔧 Troubleshooting

### Connection Issues

If clients can't connect from different networks:

1. **Wait for Propagation**: Hidden services take 10-30 seconds to propagate
2. **Test Connectivity**:
    ```bash
    python test_connection.py your_onion_address.onion
    ```
3. **Restart Components**:
    ```bash
    python kill_tor.py  # Kill existing Tor processes
    # Then restart server
    ```

### Server Won't Start

```bash
# Kill conflicting Tor processes
python kill_tor.py

# Try different approach
brew services stop tor  # On macOS
sudo service tor stop   # On Linux

# Then start the server
python anon_messenger.py --server
```

### Client Connection Timeouts

-   **Wait longer**: Hidden services can take 2-3 minutes to be fully accessible
-   **Check server**: Ensure server is still running and displays "Server Ready"
-   **Network**: Try from a different network/device to test
-   **Tor status**: Ensure Tor is running on client machine

## 🔄 Contributing

This is a minimal PoC. Contributions welcome for:

-   Enhanced security features
-   Better error handling
-   Additional cryptographic protocols
-   User interface improvements

## ⚖️ Legal Notice

Use responsibly and in accordance with local laws. This tool is for educational and legitimate privacy purposes only.
