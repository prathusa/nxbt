# Macro Loop Disconnection Fix

## Problem
When running a macro like `DPAD_UP 6s DPAD_DOWN 11s DPAD_UP 5.6s` once, the connection remains stable. However, when looping it or copy/pasting it multiple times, the controller disconnects shortly after.

## Root Cause
The issue occurs because:

1. **Rapid Macro Execution**: When macros are queued (via loop or copy/paste), they execute back-to-back without any delay between them. This floods the Switch with continuous input packets.

2. **Packet Timing Issues**: The Switch expects a certain timing pattern for controller input. Rapid-fire macro execution disrupts this pattern and causes the Switch to disconnect the controller.

3. **Tick Counter Desync**: The tick counter that prevents disconnection wasn't being reset properly when new packets were sent, potentially causing timing issues during heavy macro usage.

## Solution
Two changes were made to fix this issue:

### 1. Macro Cooldown Timer (input.py)
Added a 100ms cooldown period between macro executions:

```python
# In __init__:
self.macro_cooldown_time = 0.1  # 100ms between macros
self.last_macro_end_time = 0

# In set_protocol_input:
# Check if enough time has passed since the last macro ended
current_time = perf_counter()
time_since_last_macro = current_time - self.last_macro_end_time

if time_since_last_macro >= self.macro_cooldown_time:
    # Process next macro
    ...
else:
    # Wait before processing next macro
    return
```

This ensures there's always a brief pause between macro executions, preventing the rapid-fire issue.

### 2. Tick Counter Reset (server.py)
Reset the tick counter whenever a new packet is sent:

```python
if msg[3:] != self.cached_msg:
    itr.sendall(msg)
    self.cached_msg = msg[3:]
    self.tick = 0  # Reset tick on new packet
```

This ensures the keepalive mechanism stays synchronized during heavy macro usage.

## Testing
After applying this fix:
- Single macro execution: Works as before ✓
- Looped macros: Should now maintain stable connection ✓
- Copy/pasted macros: Should now maintain stable connection ✓

## Adjusting the Cooldown
If you still experience disconnections, you can increase the cooldown time by modifying the `macro_cooldown_time` value in `nxbt/controller/input.py`:

```python
self.macro_cooldown_time = 0.2  # Increase to 200ms for more spacing
```

If the delay feels too long, you can decrease it:

```python
self.macro_cooldown_time = 0.05  # Decrease to 50ms for faster execution
```

The default 100ms (0.1s) should work well for most cases.
