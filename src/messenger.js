import { EphemeralIdentity } from "./crypto/identity.js";
import { MessageCrypto } from "./crypto/encryption.js";
import { OnionService } from "./network/onion-service.js";

export class AnonymousMessenger {
	constructor() {
		this.identity = new EphemeralIdentity();
		this.crypto = new MessageCrypto();
		this.onionService = new OnionService();
		this.isHandshakeComplete = false;
		this.currentPeer = null;
		this.connectionString = null;
	}

	// Initialize messenger and start onion service automatically
	async init() {
		console.log("🔧 Initializing anonymous messenger...");

		// Generate ephemeral identity
		this.identity.generate();
		console.log("✅ Ephemeral identity generated");

		// Start onion service automatically
		try {
			const serviceInfo = await this.onionService.start();
			this.connectionString = serviceInfo.connectionString;

			// Set up message handler
			this.onionService.onMessage(async (message, socket) => {
				await this.handleMessage(message, socket);
			});

			console.log("✅ Messenger initialized and ready!");
			console.log(`🔗 Your connection string: ${this.connectionString}`);
			console.log(
				"📋 Share this string with others to connect anonymously"
			);

			return serviceInfo;
		} catch (error) {
			console.error("❌ Failed to initialize messenger:", error);
			throw error;
		}
	}

	// Get the connection string to share
	getConnectionString() {
		return this.connectionString;
	}

	// Connect to peer using their connection string
	async connectToPeer(connectionString) {
		try {
			console.log("🔌 Connecting to peer...");

			const connection = await this.onionService.connectToPeer(
				connectionString
			);
			this.currentPeer = connection.socket;

			// Set up peer message handlers for TCP socket
			this.currentPeer.on("data", async (data) => {
				try {
					// Handle multiple JSON messages separated by newlines
					const messages = data
						.toString()
						.split("\n")
						.filter((msg) => msg.trim());
					for (const msgStr of messages) {
						try {
							const message = JSON.parse(msgStr);
							await this.handleMessage(message, this.currentPeer);
						} catch (parseError) {
							console.error("Invalid JSON message:", parseError);
						}
					}
				} catch (error) {
					console.error("Error parsing message data:", error);
				}
			});

			this.currentPeer.on("close", () => {
				console.log("👋 Peer disconnected");
				this.currentPeer = null;
				this.isHandshakeComplete = false;
			});

			this.currentPeer.on("error", (error) => {
				console.error("❌ Peer connection error:", error);
				this.currentPeer = null;
				this.isHandshakeComplete = false;
			});

			// Initiate handshake
			await this.initiateHandshake();

			console.log("✅ Connected to peer successfully");
			return true;
		} catch (error) {
			console.error("❌ Failed to connect to peer:", error);
			return false;
		}
	}

	// Initiate handshake (client sends first)
	async initiateHandshake() {
		const handshakeMessage = {
			type: "handshake",
			publicKey: this.identity.getPublicKey().toString("base64"),
			nonce: this.identity.generateNonce().toString("base64"),
		};

		if (this.currentPeer) {
			this.currentPeer.write(JSON.stringify(handshakeMessage) + "\n");
		} else {
			this.onionService.sendMessage(handshakeMessage);
		}

		console.log("🤝 Handshake initiated");
	}

	// Handle incoming messages
	async handleMessage(message, socket) {
		switch (message.type) {
			case "handshake":
				await this.handleHandshake(message, socket);
				break;
			case "handshake_response":
				await this.handleHandshakeResponse(message, socket);
				break;
			case "encrypted_message":
				await this.handleEncryptedMessage(message, socket);
				break;
			default:
				console.log("❓ Unknown message type:", message.type);
		}
	}

	// Handle handshake message (server responds)
	async handleHandshake(message, socket) {
		try {
			console.log("🤝 Received handshake from peer");
			const theirPublicKey = Buffer.from(message.publicKey, "base64");

			// Perform ECDH (now async)
			const success = await this.crypto.performHandshake(
				this.identity.getPrivateKey(),
				theirPublicKey
			);

			if (success) {
				// Send handshake response
				const response = {
					type: "handshake_response",
					publicKey: this.identity.getPublicKey().toString("base64"),
					nonce: this.identity.generateNonce().toString("base64"),
				};

				socket.write(JSON.stringify(response) + "\n");
				this.isHandshakeComplete = true;
				this.currentPeer = socket;

				console.log("✅ Handshake complete - Ready to chat!");
			} else {
				console.log(
					"❌ Handshake failed - could not establish shared secret"
				);
			}
		} catch (error) {
			console.error("❌ Handshake failed:", error.message);
		}
	}

	// Handle handshake response (client completes handshake)
	async handleHandshakeResponse(message, socket) {
		try {
			console.log("🤝 Received handshake response");
			const theirPublicKey = Buffer.from(message.publicKey, "base64");

			// Perform ECDH (now async)
			const success = await this.crypto.performHandshake(
				this.identity.getPrivateKey(),
				theirPublicKey
			);

			if (success) {
				this.isHandshakeComplete = true;
				console.log("✅ Handshake complete - Ready to chat!");
			} else {
				console.log(
					"❌ Handshake failed - could not establish shared secret"
				);
			}
		} catch (error) {
			console.error("❌ Handshake failed:", error.message);
		}
	}

	// Handle encrypted message
	async handleEncryptedMessage(message, socket) {
		if (!this.isHandshakeComplete) {
			console.log("⚠️ Received message before handshake complete");
			return;
		}

		try {
			const encryptedData = {
				encrypted: Buffer.from(message.encrypted, "base64"),
				iv: Buffer.from(message.iv, "base64"),
				tag: Buffer.from(message.tag, "base64"),
				counter: message.counter,
			};

			const decryptedMessage = await this.crypto.decrypt(encryptedData);
			console.log(`💬 Peer: ${decryptedMessage}`);
		} catch (error) {
			console.error("❌ Failed to decrypt message:", error.message);
		}
	}

	// Send encrypted message
	async sendMessage(text) {
		if (!this.isHandshakeComplete) {
			console.log("⚠️ Cannot send message - handshake not complete");
			return false;
		}

		if (!this.isConnected()) {
			console.log("⚠️ Cannot send message - not connected");
			return false;
		}

		try {
			const encryptedData = await this.crypto.encrypt(text);

			const message = {
				type: "encrypted_message",
				encrypted: encryptedData.encrypted.toString("base64"),
				iv: encryptedData.iv.toString("base64"),
				tag: encryptedData.tag.toString("base64"),
				counter: encryptedData.counter,
			};

			if (this.currentPeer) {
				this.currentPeer.write(JSON.stringify(message) + "\n");
			} else {
				this.onionService.sendMessage(message);
			}

			return true;
		} catch (error) {
			console.error("❌ Failed to send message:", error.message);
			return false;
		}
	}

	// Check if connected and ready
	isReady() {
		return this.isHandshakeComplete && this.isConnected();
	}

	// Check if connected to a peer
	isConnected() {
		const status = this.onionService.getStatus();
		return (
			status.isRunning &&
			(status.connections > 0 ||
				(this.currentPeer && !this.currentPeer.destroyed))
		);
	}

	// Get connection status
	getStatus() {
		const onionStatus = this.onionService.getStatus();
		return {
			...onionStatus,
			handshakeComplete: this.isHandshakeComplete,
			ready: this.isReady(),
			hasActivePeer: this.currentPeer && !this.currentPeer.destroyed,
		};
	}

	// Cleanup and destroy
	async destroy() {
		console.log("🧹 Cleaning up messenger...");

		// Close current peer connection
		if (this.currentPeer && !this.currentPeer.destroyed) {
			this.currentPeer.destroy();
		}
		this.currentPeer = null;
		this.isHandshakeComplete = false;

		// Stop onion service
		await this.onionService.stop();

		// Clear sensitive data
		this.connectionString = null;
		this.identity = null;
		this.crypto = null;

		console.log("✅ Messenger destroyed and data wiped");
	}
}
