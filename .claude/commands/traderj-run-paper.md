Run the TraderJ paper trading engine in the background so it survives sleep mode and terminal close.

Steps:
1. Check if a paper trading process is already running (`pgrep -f "scripts.run_paper"`)
2. If already running, show the PID and ask the user if they want to stop it first
3. If not running, start the paper trading engine with:
   ```
   cd /Users/whoana/DEV/workspaces/claude-code/traderj
   nohup caffeinate -i .venv/bin/python -u -m scripts.run_paper $ARGUMENTS > logs/paper_trading.log 2>&1 &
   ```
   - `caffeinate -i` prevents the system from idle-sleeping while the process runs
   - `nohup` keeps it running after terminal close
   - `-u` (unbuffered) ensures real-time log output
   - Default strategy: STR-005 (or user-specified strategies)
   - Logs saved to `logs/paper_trading.log`
4. Create `logs/` directory if it doesn't exist
5. Save the PID to `logs/paper_trading.pid` for easy management
6. Show the user:
   - The PID of the running process
   - How to check logs: `tail -f logs/paper_trading.log`
   - How to stop: `kill $(cat logs/paper_trading.pid)`
7. Tail the last 20 lines of the log to confirm it started successfully

Arguments: $ARGUMENTS (optional strategy IDs, e.g., "STR-001 STR-002", default: STR-005)
