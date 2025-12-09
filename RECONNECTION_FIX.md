# NXBT Manager Reconnection Fix

## Problem
The NXBT web application was experiencing "No such file or directory" errors when the multiprocessing manager connection was lost. This occurred because:

1. The multiprocessing Manager uses Unix domain sockets for IPC (Inter-Process Communication)
2. When the manager process dies or crashes, the socket file is removed
3. Subsequent attempts to access `nxbt.state` or other shared resources fail with `FileNotFoundError`
4. The web app had no recovery mechanism for this scenario

## Solution

### Backend Changes (nxbt/web/app.py)

#### 1. Manager Health Checking
Added `check_nxbt_alive()` function that proactively checks if the manager is responsive:
```python
def check_nxbt_alive():
    """Check if NXBT manager is still alive and responsive"""
    if nxbt is None:
        return False
    
    try:
        _ = nxbt.state.copy()
        return True
    except (FileNotFoundError, EOFError, ConnectionRefusedError, BrokenPipeError, OSError):
        return False
```

#### 2. Manager Reset/Recovery
Added `reset_nxbt()` function to safely recreate the NXBT instance:
```python
def reset_nxbt():
    """Reset the NXBT instance (for recovery from crashes)"""
    global nxbt, nxbt_init_failed, nxbt_restart_count
    
    with nxbt_lock:
        if nxbt is not None:
            try:
                nxbt._on_exit()  # Cleanup old instance
            except Exception as e:
                print(f"Error during NXBT cleanup: {e}")
        
        nxbt = None
        nxbt_init_failed = False
        nxbt_restart_count += 1
        
        if nxbt_restart_count > MAX_NXBT_RESTARTS:
            raise RuntimeError("NXBT restart limit exceeded")
```

#### 3. Proactive Health Checks
All socket handlers now check manager health before operations:
- `on_state()` - Checks health and attempts recovery if dead
- `on_disconnect()` - Skips cleanup if manager is dead
- `on_shutdown()` - Validates manager before shutdown
- `web_create_pro_controller()` - Recovers manager before creating controller
- `web_reconnect_controller()` - Recovers manager before reconnecting
- `handle_input()` - Silently ignores input if manager is dead
- `handle_macro()` - Reports error if manager is dead

#### 4. New Socket Events
Added new events for frontend communication:
- `manager_reconnected` - Emitted when manager successfully recovers
- `manager_dead` - Emitted when manager cannot be recovered
- `controller_crashed` - Emitted when a controller crashes
- `controller_error` - Emitted for controller-specific errors

#### 5. Manual Reset Endpoint
Added `reset_manager` socket handler for manual recovery:
```python
@sio.on('reset_manager')
def on_reset_manager():
    """Manually reset the NXBT manager (for recovery)"""
    try:
        reset_nxbt()
        nx = get_nxbt()
        emit('manager_reset', {'message': 'NXBT manager reset successfully'})
    except Exception as e:
        emit('error', f'Failed to reset manager: {str(e)}')
```

### Frontend Changes (nxbt/web/static/js/main.js)

#### 1. Manager Reconnection Handler
```javascript
socket.on('manager_reconnected', function(data) {
    console.log("NXBT manager reconnected:", data.message);
    displayError("NXBT Manager Reconnected: " + data.message);
    NXBT_CONTROLLER_INDEX = false;
    // Return to controller selection
    HTML_CONTROLLER_CONFIG.classList.add('hidden');
    HTML_LOADER.classList.add('hidden');
    HTML_CONTROLLER_SELECTION.classList.remove('hidden');
});
```

#### 2. Manager Death Handler
```javascript
socket.on('manager_dead', function(data) {
    console.error("NXBT manager is dead:", data.error);
    displayError("NXBT Manager Failed: " + data.error + " - Please restart the webapp");
    changeStatusIndicatorState("indicator-red", "MANAGER DEAD");
});
```

#### 3. Controller Error Handlers
```javascript
socket.on('controller_crashed', function(index) {
    displayError("Controller #" + index + " has crashed. Please recreate it.");
    if (index === NXBT_CONTROLLER_INDEX) {
        changeStatusIndicatorState("indicator-red", "CRASHED");
    }
});

socket.on('controller_error', function(data) {
    displayError("Controller Error: " + data.error);
});
```

## How It Works

### Normal Operation
1. User creates a controller
2. Manager is healthy and responsive
3. Input flows normally through the manager to the controller

### Manager Crash Scenario
1. Manager process dies (crash, OOM, signal, etc.)
2. Socket file is removed from `/tmp`
3. Next `on_state()` call detects manager is dead via `check_nxbt_alive()`
4. `reset_nxbt()` is called to cleanup and recreate the manager
5. Frontend receives `manager_reconnected` event
6. User is returned to controller selection screen
7. User can create a new controller with the fresh manager

### Recovery Limits
- Maximum of 3 automatic restarts (`MAX_NXBT_RESTARTS = 3`)
- After 3 restarts, manual webapp restart is required
- This prevents infinite restart loops in case of persistent issues

## Common Causes of Manager Death

1. **Permission Issues**: `/tmp` directory permissions
   ```bash
   sudo chmod 1777 /tmp
   ```

2. **Stale Socket Files**: Previous crash left socket files
   ```bash
   sudo rm -f /tmp/pymp-*
   ```

3. **Out of Memory**: Manager process killed by OOM killer
   - Check system logs: `dmesg | grep -i kill`
   - Monitor memory: `free -h`

4. **Bluetooth Adapter Issues**: Adapter disconnected or reset
   - Check adapter: `hciconfig -a`
   - Reset adapter: `sudo hciconfig hci0 reset`

## Testing the Fix

### Test 1: Simulate Manager Death
```python
# In a Python shell while webapp is running
import os
import signal

# Find the manager process
# ps aux | grep python | grep nxbt

# Kill the manager process
os.kill(MANAGER_PID, signal.SIGKILL)

# The webapp should automatically recover
```

### Test 2: Manual Reset
```javascript
// In browser console
socket.emit('reset_manager');
```

### Test 3: Stress Test
```bash
# Create controller, kill manager, repeat
for i in {1..5}; do
    echo "Test iteration $i"
    # Create controller via webapp
    sleep 5
    # Kill manager
    pkill -9 -f "nxbt.*manager"
    sleep 2
done
```

## Monitoring

### Backend Logs
The webapp now logs manager state changes:
```
Initializing NXBT manager...
NXBT manager initialized successfully
NXBT manager connection lost: [Errno 2] No such file or directory
NXBT manager not alive - attempting recovery...
Manual NXBT manager reset requested
```

### Frontend Indicators
- Status indicator shows "MANAGER DEAD" when recovery fails
- Error messages appear for 10 seconds
- Console logs all manager events

## Troubleshooting

### Manager Won't Recover
1. Check `/tmp` permissions: `ls -la /tmp`
2. Clear stale sockets: `sudo rm -f /tmp/pymp-*`
3. Restart the webapp completely
4. Check system resources: `free -h` and `df -h`

### Frequent Manager Crashes
1. Check system logs: `journalctl -xe`
2. Monitor Bluetooth: `sudo btmon`
3. Check for hardware issues: `dmesg | grep -i bluetooth`
4. Verify BlueZ version: `bluetoothctl --version`

### Recovery Limit Reached
```
ERROR: NXBT has been restarted 3 times. Manual intervention required.
```
This means there's a persistent issue. Restart the webapp and investigate the root cause.

## Future Improvements

1. **Persistent State**: Save controller configurations to survive manager restarts
2. **Automatic Controller Recreation**: Recreate controllers after manager recovery
3. **Health Monitoring**: Periodic health checks instead of reactive detection
4. **Graceful Degradation**: Queue inputs during recovery instead of dropping them
5. **Better Diagnostics**: Capture manager crash logs for debugging

## Related Files

- `nxbt/web/app.py` - Backend socket handlers and manager lifecycle
- `nxbt/web/static/js/main.js` - Frontend event handlers
- `nxbt/nxbt.py` - Core NXBT manager implementation
- `nxbt/controller/server.py` - Controller server implementation

## References

- Python multiprocessing: https://docs.python.org/3/library/multiprocessing.html
- Unix domain sockets: https://en.wikipedia.org/wiki/Unix_domain_socket
- Flask-SocketIO: https://flask-socketio.readthedocs.io/
