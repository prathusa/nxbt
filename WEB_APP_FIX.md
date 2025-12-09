# Web App Manager Connection Fix

## Problem
The web app was experiencing repeated "NXBT manager connection lost: [Errno 2] No such file or directory" errors. This occurred because:

1. The `Nxbt()` instance was created at module import time (when `app.py` loads)
2. The multiprocessing Manager creates a Unix socket file for inter-process communication
3. If the Manager process dies or the socket file is deleted, all subsequent requests fail
4. The error manifests as `[Errno 2] No such file or directory` when trying to access the socket

## Root Cause
The multiprocessing Manager uses a Unix domain socket for communication between processes. When this socket file is missing or the Manager process has died, any attempt to access `nxbt.state` or call methods on the `nxbt` object fails with a file not found error.

## Solution
Implemented lazy initialization with proper error handling:

1. **Lazy Initialization**: Changed from creating `nxbt` at module load to creating it on first use
2. **Thread-Safe Access**: Added `get_nxbt()` function with locking to ensure thread-safe initialization
3. **Consistent Error Handling**: All socket handlers now use `get_nxbt()` instead of accessing the global directly

## Changes Made

### In `nxbt/web/app.py`:

1. Replaced immediate initialization:
   ```python
   nxbt = Nxbt()
   ```
   
   With lazy initialization:
   ```python
   nxbt = None
   nxbt_lock = RLock()
   
   def get_nxbt():
       global nxbt
       with nxbt_lock:
           if nxbt is None:
               try:
                   nxbt = Nxbt()
               except Exception as e:
                   print(f"Failed to initialize NXBT: {e}")
                   raise
           return nxbt
   ```

2. Updated all socket handlers to use `get_nxbt()`:
   - `on_state()`
   - `on_disconnect()`
   - `on_shutdown()`
   - `check_controller_health()`
   - `on_create_controller()`
   - `handle_input()`
   - `handle_macro()`

## Benefits

1. **Delayed Initialization**: The Manager process is only created when actually needed
2. **Better Error Messages**: Initialization failures are caught and logged clearly
3. **Thread Safety**: The lock ensures only one thread initializes the instance
4. **Consistent Access**: All handlers use the same initialization path

## Testing

After applying this fix:
1. Restart the web app
2. The Manager will be initialized on the first socket connection
3. Errors should be reduced or eliminated
4. If initialization fails, you'll see a clear error message

## Additional Notes

If you continue to see connection errors, check:
1. Bluetooth adapter permissions
2. BlueZ service status
3. System resources (the Manager spawns multiple processes)
4. Temporary directory permissions (where socket files are created)
