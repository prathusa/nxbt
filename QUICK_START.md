# Quick Start Guide - Automatic Connection

## Installation

1. **Install the updated package:**
   ```bash
   sudo pip3 install -e .
   ```

2. **Verify dependencies:**
   ```bash
   sudo python3 check_agent_status.py
   ```

## Usage

### Basic Example
```python
import nxbt

# Create NXBT instance (agent auto-registers)
nx = nxbt.Nxbt()

# Create controller
controller_idx = nx.create_controller(nxbt.PRO_CONTROLLER)

# Wait for Switch to connect (automatic!)
nx.wait_for_connection(controller_idx)

# Use the controller
nx.press_buttons(controller_idx, [nxbt.Buttons.A])
```

### Testing
```bash
# Run the test script
sudo python3 test_auto_connect.py
```

## What Changed?

**Before:**
```bash
# Had to manually run bluetoothctl
bluetoothctl
# Then manually authorize when Switch connects
```

**After:**
```python
# Just run your script - everything is automatic!
nx = nxbt.Nxbt()  # Agent registers automatically
controller = nx.create_controller(nxbt.PRO_CONTROLLER)
# Switch connects automatically, no manual steps!
```

## Troubleshooting

### Issue: "No Bluetooth adapter found"
**Solution:** Check Bluetooth service
```bash
sudo systemctl status bluetooth
sudo systemctl start bluetooth
```

### Issue: "Permission denied"
**Solution:** Run as root
```bash
sudo python3 your_script.py
```

### Issue: "Agent already registered"
**Solution:** This is normal if another NXBT instance is running. Stop other instances first.

### Issue: Connection still requires manual approval
**Solution:** 
1. Check agent status: `sudo python3 check_agent_status.py`
2. Restart Bluetooth: `sudo systemctl restart bluetooth`
3. Try again

## Key Points

✓ **No bluetoothctl needed** - Everything is automatic
✓ **Works on first connection** - No setup required
✓ **Persistent** - Devices are trusted for future connections
✓ **Clean** - Proper cleanup on exit

## Requirements

- Root privileges (sudo)
- Python 3.6+
- BlueZ 5.x
- PyGObject >= 3.30.0 (auto-installed)

## Next Steps

1. Test with the provided test script
2. Integrate into your existing code
3. Enjoy automatic connections!

For more details, see:
- `AUTOMATIC_CONNECTION_FIX.md` - Technical details
- `CHANGES_SUMMARY.md` - Complete change list
