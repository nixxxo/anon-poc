#!/bin/bash

echo "🔒 Anonymous Terminal Messenger"
echo "================================"
echo ""
echo "Choose an option:"
echo "1. Start Server (Host a chat room)"
echo "2. Connect to Server"
echo "3. Interactive Mode"
echo ""

read -p "Enter choice (1-3): " choice

case $choice in
    1)
        echo "Starting server..."
        python anon_messenger.py --server
        ;;
    2)
        echo "Enter the connection string from the server:"
        read -p "Connection String: " conn_string
        python anon_messenger.py --client "$conn_string"
        ;;
    3)
        python anon_messenger.py
        ;;
    *)
        echo "Invalid choice. Exiting."
        exit 1
        ;;
esac 