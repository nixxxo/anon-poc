import { createInterface } from "readline";
import { AnonymousMessenger } from "./messenger.js";

export class CLI {
	constructor() {
		this.messenger = new AnonymousMessenger();
		this.rl = null;
		this.isActive = false;
		this.isInitialized = false;
	}

	async start() {
		console.log("🔒 Anonymous Messenger - Tor Edition");
		console.log("=====================================");
		console.log("🧅 Starting integrated Tor onion service...");
		console.log("⏳ Please wait, this may take a few moments...");

		this.rl = createInterface({
			input: process.stdin,
			output: process.stdout,
			prompt: "> ",
		});

		try {
			await this.messenger.init();
			this.isInitialized = true;

			this.setupSignalHandlers();
			this.showHelp();
			this.startCommandLoop();
		} catch (error) {
			console.error("❌ Failed to initialize messenger:", error.message);
			console.log(
				"💡 Make sure Tor is installed and accessible from command line"
			);
			process.exit(1);
		}
	}

	showHelp() {
		console.log("\n📖 Commands:");
		console.log(
			"  share                  - Display your connection string"
		);
		console.log(
			"  connect <string>       - Connect using a peer's connection string"
		);
		console.log(
			"  send <message>         - Send encrypted message to connected peer"
		);
		console.log(
			"  status                 - Show connection and service status"
		);
		console.log("  help                   - Show this help");
		console.log("  exit                   - Quit and wipe all data");
		console.log("");
		console.log(
			"🔗 Your connection string is ready! Use 'share' to display it."
		);
		console.log("");
	}

	startCommandLoop() {
		this.isActive = true;
		this.rl.prompt();

		this.rl.on("line", async (input) => {
			if (!this.isActive) return;

			const trimmed = input.trim();
			if (!trimmed) {
				this.rl.prompt();
				return;
			}

			const [command, ...args] = trimmed.split(" ");

			switch (command.toLowerCase()) {
				case "share":
					this.handleShare();
					break;
				case "connect":
					await this.handleConnect(args);
					break;
				case "send":
					await this.handleSend(args.join(" "));
					break;
				case "status":
					this.handleStatus();
					break;
				case "help":
					this.showHelp();
					break;
				case "exit":
				case "quit":
					await this.handleExit();
					return;
				default:
					console.log(
						`❓ Unknown command: ${command}. Type 'help' for available commands.`
					);
			}

			if (this.isActive) {
				this.rl.prompt();
			}
		});

		this.rl.on("close", async () => {
			await this.handleExit();
		});
	}

	handleShare() {
		if (!this.isInitialized) {
			console.log("⚠️ Messenger not initialized yet");
			return;
		}

		const connectionString = this.messenger.getConnectionString();
		console.log("\n🔗 Your Connection String:");
		console.log("━".repeat(50));
		console.log(connectionString);
		console.log("━".repeat(50));
		console.log(
			"📋 Copy this string and share it with someone you want to chat with."
		);
		console.log(
			"🔒 This contains your onion address and encryption parameters."
		);
		console.log("");
	}

	async handleConnect(args) {
		if (!this.isInitialized) {
			console.log("⚠️ Messenger not initialized yet");
			return;
		}

		if (args.length === 0) {
			console.log("Usage: connect <connection_string>");
			console.log(
				"📝 Paste the connection string you received from your peer"
			);
			return;
		}

		const connectionString = args.join(" ");

		if (!connectionString) {
			console.log("❌ Empty connection string provided");
			return;
		}

		console.log("🔌 Connecting to peer...");
		console.log("⏳ This may take a moment through Tor network...");

		const success = await this.messenger.connectToPeer(connectionString);

		if (success) {
			console.log(
				"✅ Successfully connected! You can now send messages."
			);
		} else {
			console.log(
				"❌ Connection failed. Please check the connection string and try again."
			);
		}
	}

	async handleSend(message) {
		if (!this.isInitialized) {
			console.log("⚠️ Messenger not initialized yet");
			return;
		}

		if (!message.trim()) {
			console.log("Usage: send <message>");
			console.log("📝 Type your message after the 'send' command");
			return;
		}

		if (!this.messenger.isReady()) {
			console.log(
				"❌ Cannot send - not connected to a peer or handshake incomplete"
			);
			console.log("💡 Use 'connect <string>' to connect to a peer first");
			return;
		}

		try {
			const success = await this.messenger.sendMessage(message);
			if (success) {
				console.log(`📤 You: ${message}`);
			} else {
				console.log("❌ Failed to send message");
			}
		} catch (error) {
			console.error("❌ Error sending message:", error.message);
		}
	}

	handleStatus() {
		if (!this.isInitialized) {
			console.log("⚠️ Messenger not initialized yet");
			return;
		}

		const status = this.messenger.getStatus();

		console.log("\n📊 Status Report:");
		console.log("━".repeat(30));
		console.log(
			`🧅 Tor Service: ${status.torRunning ? "✅ Running" : "❌ Stopped"}`
		);
		console.log(
			`🌐 Onion Service: ${
				status.isRunning ? "✅ Active" : "❌ Inactive"
			}`
		);
		console.log(`🔗 Active Connections: ${status.activeConnections}`);
		console.log(
			`🤝 Handshake Complete: ${
				status.handshakeComplete ? "✅ Yes" : "❌ No"
			}`
		);
		console.log(`💬 Ready to Chat: ${status.ready ? "✅ Yes" : "❌ No"}`);
		console.log(
			`👥 Has Active Peer: ${status.hasActivePeer ? "✅ Yes" : "❌ No"}`
		);

		if (status.onionAddress) {
			console.log(
				`📍 Onion Address: ${status.onionAddress}:${status.port}`
			);
		}

		console.log("━".repeat(30));
		console.log("");
	}

	async handleExit() {
		if (!this.isActive) return;

		this.isActive = false;
		console.log("\n🛑 Shutting down...");
		console.log("🧹 Wiping sensitive data and stopping Tor...");

		if (this.isInitialized) {
			await this.messenger.destroy();
		}

		if (this.rl) {
			this.rl.close();
		}

		console.log("👋 Goodbye! All data has been securely wiped.");
		process.exit(0);
	}

	setupSignalHandlers() {
		const cleanup = async () => {
			console.log("\n🛑 Interrupt received");
			await this.handleExit();
		};

		process.on("SIGINT", cleanup);
		process.on("SIGTERM", cleanup);

		process.on("uncaughtException", (error) => {
			console.error("💥 Uncaught exception:", error);
			this.handleExit();
		});

		process.on("unhandledRejection", (reason, promise) => {
			console.error(
				"💥 Unhandled rejection at:",
				promise,
				"reason:",
				reason
			);
			this.handleExit();
		});
	}
}
