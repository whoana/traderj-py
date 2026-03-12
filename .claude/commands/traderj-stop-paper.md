Stop the TraderJ paper trading engine that was started with /traderj-run-paper.

Steps:
1. Check if `logs/paper_trading.pid` exists and read the PID
2. Check if the process is actually running (`ps -p <PID>`)
3. If running:
   - Send SIGINT (graceful shutdown, same as Ctrl+C) with `kill -INT <PID>`
   - Wait 3 seconds, then check if the process stopped
   - If still running, send SIGTERM with `kill <PID>`
   - Remove `logs/paper_trading.pid`
   - Show the last 10 lines of `logs/paper_trading.log` to confirm shutdown
4. If PID file doesn't exist or process not running:
   - Also check with `pgrep -f "scripts.run_paper"` as fallback
   - If found, kill that process
   - If not found, tell the user no paper trading process is running
5. Also kill the associated `caffeinate` parent process if it exists
