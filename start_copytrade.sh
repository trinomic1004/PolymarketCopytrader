#!/bin/bash

# Polymarket Copytrader Startup Script
# This script creates a new tmux session and runs the copytrader

SESSION_NAME="polymarket-copytrade"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COPYTRADE_CMD="/opt/homebrew/bin/python3.11 -m src.cli start --config config/settings.yaml"

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "Error: tmux is not installed. Please install it first."
    echo "Run: brew install tmux"
    exit 1
fi

# Check if system Python 3.11 is available
if ! command -v python3.11 &> /dev/null; then
    echo "Error: python3.11 is not installed or not in PATH."
    echo "Run: brew install python@3.11"
    exit 1
fi

# Check if session already exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "Session '$SESSION_NAME' already exists."
    echo "Starting copytrader inside existing session..."
    tmux send-keys -t "$SESSION_NAME" "$COPYTRADE_CMD" C-m
    tmux attach-session -t "$SESSION_NAME"
    exit 0
fi

# Create new tmux session and run the application
echo "Starting Polymarket Copytrader in tmux session '$SESSION_NAME'..."
tmux new-session -d -s "$SESSION_NAME" -c "$SCRIPT_DIR"

# Run the application using system Python 3.11 (bypassing pyenv)
tmux send-keys -t "$SESSION_NAME" "$COPYTRADE_CMD" C-m

# Attach to the session
tmux attach-session -t "$SESSION_NAME"
