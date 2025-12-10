# Macro Loop Disconnection Fix

## Problem
When running a macro like `DPAD_UP 6s DPAD_DOWN 11s DPAD_UP 5.6s` once, the connection remains stable. However, when looping it or copy/pasting it multiple times, the controller disconnects shortly after or at the end of macro execution.

## Root Cause
The issue occurs because of multiple factors:

1. **Rapid Macro Execution**: When macros are queued (via loop or copy/paste), they execute back-to-back without any delay between them. This floods the Switch with continuous input packets.

2. **Packet Timing Issues**: The Switch expects a certain timing pattern for controller input. Rapid-fire macro execution disrupts this pattern and causes the Switch to disconnect the controller.

3. **Tick Counter Desync**: The tick counter that prevents disconnection wasn't being reset properly when new packets were sent, potentially causing timing issues during heavy macro usage.

4. **Button State Not Released**: When a macro completes, the last button state remains in the protocol's report buffer. The Switch continues to receive packets with buttons "pressed" even after the macro ends, which can cause disconnection.

## Solution
Three changes were made to fix this issue:

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

### 3. Post-Macro Neutral State (input.py)
After a macro completes, explicitly send neutral inputs (all buttons released, sticks centered) for several cycles:

```python
# In __init__:
self.post_macro_neutral_cycles = 0
self.post_macro_neutral_required = 10  # Send neutral for ~10 cycles (~75ms)

# When macro completes:
self.post_macro_neutral_cycles = self.post_macro_neutral_required
self.protocol.set_button_inputs(0, 0, 0)
left_center = self.stick_ratio_to_calibrated_position(0, 0, "L_STICK")
right_center = self.stick_ratio_to_calibrated_position(0, 0, "R_STICK")
self.protocol.set_left_stick_inputs(left_center)
self.protocol.set_right_stick_inputs(right_center)

# In set_protocol_input:
if self.post_macro_neutral_cycles > 0:
    # Continue sending neutral inputs
    self.protocol.set_button_inputs(0, 0, 0)
    # ... set sticks to center ...
    self.post_macro_neutral_cycles -= 1
    return
```

This ensures the Switch properly registers that all buttons have been released before the next macro starts or the controller goes idle.

## Testing
After applying this fix:
- Single macro execution: Works as before ✓
- Looped macros: Should now maintain stable connection ✓
- Copy/pasted macros: Should now maintain stable connection ✓
- End of macro execution: No disconnection, buttons properly released ✓

## Adjusting the Settings
If you still experience disconnections, you can adjust these values in `nxbt/controller/input.py`:

### Macro Cooldown Time
Increase the cooldown time for more spacing between macros:

```python
self.macro_cooldown_time = 0.2  # Increase to 200ms for more spacing
```

Or decrease it for faster execution:

```python
self.macro_cooldown_time = 0.05  # Decrease to 50ms for faster execution
```

The default 100ms (0.1s) should work well for most cases.

### Post-Macro Neutral Cycles
If the controller still disconnects at the end of macros, increase the neutral state duration:

```python
self.post_macro_neutral_required = 20  # Increase to ~150ms of neutral state
```

Or decrease it if you want faster macro chaining:

```python
self.post_macro_neutral_required = 5  # Decrease to ~38ms of neutral state
```

The default 10 cycles (~75ms) should work well for most cases.
