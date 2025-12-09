# Web App Error Handling Improvements

## Problems Fixed

### 1. Controller Does Not Exist Errors
The web app was throwing unhandled `ValueError: Specified controller does not exist` exceptions when:
- Controllers crashed or disconnected
- Web UI continued sending input/macro commands to non-existent controller indices
- This resulted in traceback spam in the logs

### 2. Multiprocessing Manager Connection Failures
The web app was throwing `FileNotFoundError` when the multiprocessing Manager died:
- `nxbt.state.copy()` would fail with "No such file or directory"
- This happened when the controller manager process crashed
- Resulted in continuous traceback spam every time state was polled (1Hz)

## Solution

### 1. Added Error Handling to Socket Handlers

All critical handlers now catch and handle errors gracefully:

- **`on_state()`**: Catches multiprocessing connection errors and returns empty state
- **`handle_input()`**: Catches controller errors, manager failures, and emits specific error events
- **`handle_macro()`**: Same error handling as input
- **`on_shutdown()`**: Handles cleanup errors gracefully
- **`check_controller_health()`**: Detects manager death and reports it

### 2. Proactive Controller State Checking

Both `handle_input()` and `handle_macro()` now:
- Check if controller exists before attempting operations
- Detect crashed controllers and emit `controller_crashed` event
- Prevent operations on dead controllers

### 3. Improved Session Management

- **`on_disconnect()`**: Now properly cleans up USER_INFO and handles ValueError
- **`on_shutdown()`**: Cleans up user session data when controller is removed
- **`on_create_controller()`**: Automatically removes old crashed controllers before creating new ones

### 4. New Health Check Endpoint

Added `check_controller_health()` socket event:
- Allows UI to query controller state
- Returns existence and current state
- Can be used for monitoring and auto-recovery

## New Socket Events

### Emitted by Server:
- `controller_crashed` - Sent when operations attempted on crashed controller
- `controller_error` - Sent with detailed error info (index + error message)
- `controller_health` - Response to health check with state info

### Received by Server:
- `check_controller_health` - Query controller state

## Benefits

1. **No more traceback spam** - All errors are caught and handled gracefully
2. **Better user feedback** - Specific error events can be displayed in UI
3. **Automatic cleanup** - Dead controllers are removed when creating new ones
4. **Crash detection** - Operations stop when controller crashes
5. **Manager failure resilience** - Web app continues to function even if multiprocessing manager dies
6. **Silent degradation** - Input commands fail silently when manager is dead (prevents spam)

## UI Integration Recommendations

To fully leverage these improvements, the JavaScript UI should:

1. Listen for `controller_crashed` and `controller_error` events
2. Stop sending input when controller crashes
3. Show user-friendly error messages
4. Optionally implement auto-restart on crash detection
5. Use `check_controller_health` for periodic monitoring

## Example UI Handler

```javascript
socket.on('controller_crashed', function(index) {
    console.log('Controller crashed:', index);
    // Stop input loop
    // Show error message
    // Optionally auto-restart
});

socket.on('controller_error', function(data) {
    console.log('Controller error:', data.error, 'for index:', data.index);
    displayError(data.error);
});
```

## Existing UI Buttons

The UI already has these buttons that work well with the improvements:
- **Shutdown Controller**: Removes the controller
- **Recreate Controller**: Creates a new controller (now auto-cleans old one)
- **Restart Controller**: Shuts down and recreates after 2 seconds

## Root Cause Analysis

The multiprocessing manager failures indicate a deeper issue with the NXBT controller lifecycle:

1. **Controller crashes** → Manager process may die
2. **Manager dies** → All state access fails with FileNotFoundError
3. **Web app polls state at 1Hz** → Continuous errors

**Recommended Investigation:**
- Why are controllers crashing?
- Why does the manager process die?
- Check Bluetooth adapter stability
- Review controller server error handling
- Consider adding manager process monitoring/restart logic
