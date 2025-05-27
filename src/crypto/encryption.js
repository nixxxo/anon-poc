import {
	createCipheriv,
	createDecipheriv,
	randomBytes,
	createHash,
} from "crypto";

export class MessageCrypto {
	constructor() {
		this.sharedSecret = null;
		this.encryptionKey = null;
		this.messageCounter = 0;
	}

	// Perform simplified key exchange using hash-based derivation
	async performHandshake(myPrivateKey, theirPublicKey) {
		try {
			console.log("🔐 Performing simplified handshake...");

			// Create a deterministic shared secret by hashing both keys together
			const myKeyStr = myPrivateKey.toString("base64");
			const theirKeyStr = theirPublicKey.toString("base64");

			// Create deterministic shared secret by sorting and combining keys
			const keyMaterial = [myKeyStr, theirKeyStr].sort().join("|");

			// Hash the combined key material to create shared secret
			this.sharedSecret = createHash("sha256")
				.update(keyMaterial)
				.update("anon-messenger-salt")
				.digest();

			// Derive encryption key from shared secret
			this.encryptionKey = createHash("sha256")
				.update(this.sharedSecret)
				.update("encryption-key")
				.digest();

			console.log("🔐 Shared secret established (simplified)");
			return true;
		} catch (error) {
			console.error("Handshake failed:", error.message);
			return false;
		}
	}

	// Encrypt message with counter-based key derivation
	async encrypt(message) {
		if (!this.encryptionKey) {
			throw new Error("No encryption key available");
		}

		try {
			// Derive message-specific key using hash
			const messageKey = createHash("sha256")
				.update(this.encryptionKey)
				.update(this.messageCounter.toString())
				.update("message-key")
				.digest();

			const iv = randomBytes(16);
			const cipher = createCipheriv("aes-256-cbc", messageKey, iv);

			const encrypted = Buffer.concat([
				cipher.update(Buffer.from(message, "utf8")),
				cipher.final(),
			]);

			const tag = Buffer.alloc(0); // No auth tag for CBC mode
			this.messageCounter++;

			return {
				encrypted,
				iv,
				tag,
				counter: this.messageCounter - 1,
			};
		} catch (error) {
			console.error("Encryption failed:", error.message);
			throw new Error("Encryption failed");
		}
	}

	// Decrypt message
	async decrypt(encryptedData) {
		if (!this.encryptionKey) {
			throw new Error("No encryption key available");
		}

		const { encrypted, iv, tag, counter } = encryptedData;

		try {
			// Derive same message-specific key using hash
			const messageKey = createHash("sha256")
				.update(this.encryptionKey)
				.update(counter.toString())
				.update("message-key")
				.digest();

			const decipher = createDecipheriv("aes-256-cbc", messageKey, iv);

			const decrypted = Buffer.concat([
				decipher.update(encrypted),
				decipher.final(),
			]);

			return decrypted.toString("utf8");
		} catch (error) {
			console.error("Decryption failed:", error.message);
			throw new Error("Decryption failed");
		}
	}

	// Securely destroy encryption state
	destroy() {
		if (this.sharedSecret) {
			this.sharedSecret.fill(0);
		}
		if (this.encryptionKey) {
			this.encryptionKey.fill(0);
		}
		this.sharedSecret = null;
		this.encryptionKey = null;
		this.messageCounter = 0;
	}
}
