# NXBT Reconnection - Quick Usage Guide

## What Changed?

The NXBT web app now automatically recovers from manager crashes and connection losses. You'll see better error messages and the app will try to fix itself.

## What You'll See

### When Manager Reconnects Successfully
- **Message**: "NXBT Manager Reconnected: NXBT manager reconnected - please recreate controllers"
- **Action**: You'll be returned to the controller selection screen
- **What to do**: Click "Create Pro Controller" again

### When Manager Can't Recover
- **Message**: "NXBT Manager Failed: [error details] - Please restart the webapp"
- **Status**: Red indicator showing "MANAGER DEAD"
- **What to do**: Restart the webapp with `sudo nxbt webapp`

### When Controller Crashes
- **Message**: "Controller #X has crashed. Please recreate it."
- **Status**: Red indicator showing "CRASHED"
- **What to do**: Click the restart button or create a new controller

## Quick Fixes

### If you see "No such file or directory"
```bash
# Clean up stale socket files
sudo rm -f /tmp/pymp-*
sudo chmod 1777 /tmp

# Restart the webapp
sudo nxbt webapp
```

### If manager keeps crashing
```bash
# Check Bluetooth adapter
hciconfig -a

# Reset the adapter
sudo hciconfig hci0 reset

# Check system resources
free -h
df -h

# Restart the webapp
sudo nxbt webapp
```

### Manual Manager Reset
If you want to manually reset the manager without restarting the webapp:

1. Open browser console (F12)
2. Type: `socket.emit('reset_manager');`
3. Press Enter

## Best Practices

1. **Don't spam controller creation** - Wait for the previous controller to fully connect
2. **Watch the status indicator** - Green = good, Yellow = connecting, Red = problem
3. **Check the error messages** - They tell you what went wrong
4. **Restart cleanly** - Use Ctrl+C to stop the webapp, don't kill it

## Reconnection vs. New Connection

### Reconnect (Faster)
- Use when you accidentally disconnected
- Switch must still be on the same screen
- No pairing required
- Click "Reconnect" button (if available)

### New Connection (Slower)
- Use for first connection
- Use if Switch went to home screen
- Requires pairing process
- Click "Create Pro Controller"

## Troubleshooting

### "NXBT restart limit exceeded"
The manager crashed 3 times in a row. This means there's a bigger problem:
1. Restart the webapp completely
2. Check system logs: `journalctl -xe`
3. Check Bluetooth: `sudo btmon`
4. Make sure your adapter is working: `hciconfig`

### Controllers keep disconnecting
This is usually a Bluetooth issue, not a manager issue:
1. Move closer to the Switch
2. Remove other Bluetooth devices
3. Reset the Bluetooth adapter
4. Check for interference

### Input lag or freezing
1. Check CPU usage: `top`
2. Check memory: `free -h`
3. Close other applications
4. Try a different Bluetooth adapter

## Technical Details

- **Recovery Time**: ~2-3 seconds
- **Max Auto-Restarts**: 3 times
- **Health Check Interval**: Every state request (~1 second)
- **Socket Timeout**: Immediate (non-blocking)

## When to Restart the Webapp

Restart if you see:
- "NXBT restart limit exceeded"
- "MANAGER DEAD" that won't clear
- Persistent connection issues
- Memory or resource warnings

Don't restart for:
- Single controller crashes (just recreate)
- Temporary disconnections (use reconnect)
- Input errors (check your controller)

## Getting Help

If problems persist:
1. Check the logs in the terminal where you started the webapp
2. Look for error messages in the browser console (F12)
3. Check system logs: `journalctl -xe | grep -i bluetooth`
4. Report issues with full error messages and logs
