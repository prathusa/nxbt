# NXBT Reconnection Fix

## Problem

The reconnection feature wasn't working because:

1. **MAC Address Mismatch**: The Nintendo Switch remembers the controller's Bluetooth MAC address during initial pairing. When reconnecting, the Switch expects the same MAC address, but the adapter might have a different MAC (especially after system restarts or if using different adapters).

2. **No State Persistence**: There was no mechanism to store and restore the MAC address used during the initial successful connection.

3. **Missing Trust Relationship**: The Switch device wasn't always being properly trusted in BlueZ, which is required for reconnection.

## Solution

### 1. Connection State Persistence

Added functions to store and retrieve connection state in `~/.nxbt/connection_state.json`:

- `save_connection_state()`: Saves adapter MAC, Switch addresses, and original adapter MAC
- `load_connection_state()`: Loads previously saved state
- `update_connection_state()`: Updates state after successful connection
- `get_adapter_controller_mac()`: Gets the stored MAC for an adapter
- `get_stored_switch_addresses()`: Gets all stored Switch addresses

### 2. MAC Address Restoration

Added `prepare_for_reconnect()` method to BlueZ class that:
- Checks for a stored controller MAC address
- Restores the adapter's MAC to match what was used during initial pairing
- Logs the restoration process for debugging

### 3. Enhanced Switch Address Discovery

Updated `get_switch_addresses()` to combine:
- BlueZ discovered devices (currently known)
- Stored addresses from previous connections (persists across restarts)

### 4. Automatic State Saving

Connection info is now automatically saved:
- After successful initial connection in `connect()`
- After successful reconnection in `reconnect()`

## How It Works

### First Connection (Change Grip/Order Menu)

1. Controller sets up and waits for Switch to connect
2. Switch connects and pairing completes
3. **NEW**: Connection state is saved (adapter MAC + Switch address)
4. Controller is ready for use

### Reconnection (Home Screen)

1. **NEW**: `prepare_for_reconnect()` restores the stored MAC address
2. Controller attempts to connect to stored Switch addresses
3. Switch recognizes the MAC and accepts the connection
4. **NEW**: Connection state is updated
5. Controller is ready for use

## State File Format

```json
{
  "adapters": {
    "hci0": {
      "original_mac": "AA:BB:CC:DD:EE:FF",
      "controller_mac": "7C:BB:8A:XX:XX:XX",
      "switch_addresses": [
        "XX:XX:XX:XX:XX:XX"
      ]
    }
  }
}
```

## Usage

No changes to the API - reconnection now works automatically:

```python
import nxbt

nx = nxbt.Nxbt()

# Get all known Switch addresses (now includes stored addresses)
addresses = nx.get_switch_addresses()

# Create controller with reconnect (MAC is automatically restored)
controller_index = nx.create_controller(
    nxbt.PRO_CONTROLLER,
    reconnect_address=addresses
)
```

## Troubleshooting

### Reconnection Still Fails

1. **Delete state file**: `rm ~/.nxbt/connection_state.json`
2. **Re-pair from Change Grip/Order menu**
3. **Try reconnecting again**

### MAC Address Not Being Set

Some Bluetooth adapters don't support MAC address changes. Check:
```bash
hcitool -i hci0 cmd 0x3f 0x001 0x00 0x00 0x00 0x00 0x00 0x00
```

If this fails, your adapter may not support MAC spoofing.

### Switch Not Recognizing Controller

1. On Switch: Go to Controllers > Change Grip/Order
2. Remove the controller from Switch's paired list
3. Re-pair using NXBT
4. Future reconnections should work from Home Screen
