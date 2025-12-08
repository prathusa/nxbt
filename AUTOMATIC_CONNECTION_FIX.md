# Automatic Connection Fix

## Problem
Previously, NXBT required manual intervention via `bluetoothctl` to accept incoming connections from the Nintendo Switch. The Switch would request authorization, but without an agent registered to handle these requests, the connection would fail unless manually approved.

## Solution
The code has been updated to automatically handle pairing and authorization requests from the Nintendo Switch by implementing a DBus agent that:

1. **Auto-accepts all pairing requests** - No manual confirmation needed
2. **Auto-authorizes service connections** - Automatically approves HID service connections
3. **Trusts connected devices** - Marks the Switch as trusted for future connections
4. **Handles all agent callbacks** - Implements all required DBus agent methods

## Changes Made

### 1. `nxbt/bluez.py`
- Added `AutoAcceptAgent` class that implements the BlueZ Agent1 interface
- Registers the agent automatically when BlueZ is initialized
- Agent handles all authorization/pairing callbacks automatically
- Added `trust_device()` method to mark devices as trusted
- Added proper cleanup in `close()` method

### 2. `nxbt/controller/server.py`
- Automatically trusts the Switch device after connection
- Properly cleans up the agent on exit

### 3. `setup.py`
- Added `PyGObject>=3.30.0` dependency for DBusGMainLoop support

## Testing

Run the test script to verify automatic connection:

```bash
sudo python3 test_auto_connect.py
```

**Steps:**
1. Run the script as root (required for Bluetooth operations)
2. Go to your Switch's "Change Grip/Order" menu
3. The controller should appear and connect automatically
4. No bluetoothctl intervention required!

## Technical Details

The agent implements the following DBus methods:
- `AuthorizeService` - Auto-approves service connections
- `RequestAuthorization` - Auto-authorizes connection requests
- `RequestConfirmation` - Auto-confirms pairing
- `RequestPinCode` / `RequestPasskey` - Provides default credentials
- `DisplayPasskey` / `DisplayPinCode` - No-op for headless operation
- `Cancel` - Handles request cancellations
- `Release` - Cleanup on agent unregistration

The agent is registered with "NoInputNoOutput" capability, which tells BlueZ that this device has no input/output capabilities and should auto-accept connections.

## Requirements

- Python 3.6+
- dbus-python >= 1.2.16
- PyGObject >= 3.30.0
- BlueZ 5.x
- Root privileges (for Bluetooth operations)

## Notes

- The agent is automatically registered when BlueZ is initialized
- The agent is set as the default agent for the system
- Devices are automatically trusted after first connection
- The agent is properly cleaned up on exit
