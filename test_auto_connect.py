#!/usr/bin/env python3
"""
Test script to verify automatic connection handling with Nintendo Switch.
This script creates a Pro Controller and waits for the Switch to connect.
No manual bluetoothctl intervention should be required.
"""

import nxbt

# Create an NXBT instance
nx = nxbt.Nxbt()

print("Creating Pro Controller...")
print("The controller should now be discoverable.")
print("Go to your Switch's 'Change Grip/Order' menu to connect.")
print("The connection should happen automatically without requiring bluetoothctl!")

# Create a Pro Controller
controller_index = nx.create_controller(nxbt.PRO_CONTROLLER)

print(f"Controller created with index: {controller_index}")
print("Waiting for Switch to connect...")

# Wait for the Switch to connect
nx.wait_for_connection(controller_index)

print("Connected successfully!")
print("Testing button press...")

# Press the A button as a test
nx.press_buttons(controller_index, [nxbt.Buttons.A])

print("Test complete! The controller should have pressed the A button.")
print("Press Ctrl+C to exit.")

# Keep the script running
try:
    import time
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nExiting...")
    nx.remove_controller(controller_index)
