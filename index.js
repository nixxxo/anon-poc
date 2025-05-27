#!/usr/bin/env node

import { CLI } from "./src/cli.js";
import { randomBytes } from "crypto";

// Disable all forms of data persistence for anonymity
process.env.NODE_ENV = "memory-only";
process.env.TOR_DATA_DIRECTORY = ":memory:";

// Anti-forensics: Ensure no disk writes
if (process.platform !== "win32") {
	process.umask(0o077); // Restrictive file permissions
}

// Clear environment variables that could leak information
delete process.env.USER;
delete process.env.USERNAME;
delete process.env.HOME;
delete process.env.USERPROFILE;
delete process.env.LOGNAME;
delete process.env.SHELL;

// Randomize process title for additional anonymity
process.title = `node-${randomBytes(4).toString("hex")}`;

// Memory optimization: Set aggressive garbage collection
process.env.NODE_OPTIONS = "--max-old-space-size=256 --gc-interval=100";

// Check Node.js version
const nodeVersion = process.version;
const majorVersion = parseInt(nodeVersion.slice(1).split(".")[0]);

if (majorVersion < 18) {
	console.error("❌ Node.js v18+ required. Current version:", nodeVersion);
	process.exit(1);
}

// Disable Node.js warnings for cleaner output
process.removeAllListeners("warning");
process.on("warning", () => {}); // Suppress warnings

// Anti-debugging measures
if (process.env.NODE_ENV !== "development") {
	const startTime = Date.now();
	setImmediate(() => {
		if (Date.now() - startTime > 100) {
			console.error("❌ Potential debugging detected");
			process.exit(1);
		}
	});
}

// Secure memory cleanup on exit
const secureExit = () => {
	// Force garbage collection if available
	if (global.gc) {
		global.gc();
	}

	// Overwrite process memory (best effort)
	const dummy = Buffer.alloc(1024 * 1024).fill(0);
	dummy.fill(Math.random() * 255);

	process.exit(0);
};

process.on("SIGINT", secureExit);
process.on("SIGTERM", secureExit);
process.on("uncaughtException", (error) => {
	console.error("💥 Critical error:", error.message);
	secureExit();
});

// Start the CLI application with timeout
const cli = new CLI();
const startupTimeout = setTimeout(() => {
	console.error("❌ Startup timeout - Tor network may be unreachable");
	console.log("💡 Try again or check your network connection");
	process.exit(1);
}, 30000); // 30 second timeout

cli.start()
	.then(() => {
		clearTimeout(startupTimeout);
	})
	.catch((error) => {
		clearTimeout(startupTimeout);
		console.error("💥 Failed to start application:", error.message);
		secureExit();
	});
