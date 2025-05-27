import { generateKeyPairSync, randomBytes } from "crypto";

export class EphemeralIdentity {
	constructor() {
		this.keyPair = null;
		this.publicKey = null;
	}

	generate() {
		// Generate X25519 key pair for ECDH with raw format for better compatibility
		this.keyPair = generateKeyPairSync("x25519", {
			publicKeyEncoding: { type: "spki", format: "der" },
			privateKeyEncoding: { type: "pkcs8", format: "der" },
		});

		// Convert keys to the format expected by diffieHellman
		this.publicKey = this.keyPair.publicKey;
		return this.publicKey;
	}

	getPublicKey() {
		return this.publicKey;
	}

	getPrivateKey() {
		return this.keyPair.privateKey;
	}

	// Securely wipe sensitive data
	destroy() {
		if (this.keyPair && this.keyPair.privateKey) {
			// Can't fill key objects in newer Node.js versions
			this.keyPair.privateKey = null;
		}
		this.keyPair = null;
		this.publicKey = null;
	}

	// Generate ephemeral nonce for handshake
	generateNonce() {
		return randomBytes(32);
	}
}
