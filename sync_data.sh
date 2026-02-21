#!/bin/bash
# Syncs live bot state files to data/ and pushes to GitHub + Vercel.
# Run this periodically (e.g. every 5 min via cron) to keep the dashboard updated.
#
# Usage: ./sync_data.sh

set -e
cd "$(dirname "$0")"

STATE_DIR="$HOME/.insider_researcher"

echo "Copying state files..."
cp "$STATE_DIR/dual_whale_v4_state.json" data/ 2>/dev/null || true
cp "$STATE_DIR/polymanager_state.json" data/ 2>/dev/null || true
cp "$STATE_DIR/elon_tweet_bot_state.json" data/ 2>/dev/null || true

echo "Committing changes..."
git add data/
git commit -m "Update dashboard data $(date +%Y-%m-%d_%H:%M)" 2>/dev/null || echo "No changes to commit"

echo "Pushing to GitHub..."
git push origin main 2>/dev/null || echo "Push failed"

echo "Done! Vercel will auto-deploy from GitHub."
