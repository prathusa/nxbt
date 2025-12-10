#!/usr/bin/env python3
"""
Test script for verifying NXBT reconnection functionality.

This script tests the reconnection feature by:
1. Checking for stored connection state
2. Attempting to reconnect to a previously connected Switch
3. Verifying the connection works

Usage:
    sudo python3 scripts/test_reconnect.py

Requirements:
- Must have previously connected to a Switch using NXBT
- Switch should be on the Home Screen (not Change Grip/Order menu)
"""

import sys
import time
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    print("=" * 60)
    print("NXBT Reconnection Test")
    print("=" * 60)
    
    # Check for root privileges
    if os.geteuid() != 0:
        print("ERROR: This script must be run as root (sudo)")
        sys.exit(1)
    
    # Import after path setup
    from nxbt.bluez import load_connection_state, get_stored_switch_addresses
    import nxbt
    
    # Check stored connection state
    print("\n1. Checking stored connection state...")
    state = load_connection_state()
    
    if not state or 'adapters' not in state:
        print("   No stored connection state found.")
        print("   You need to connect to a Switch first using the Change Grip/Order menu.")
        print("   Run: sudo nxbt demo")
        sys.exit(1)
    
    print(f"   Found state for {len(state['adapters'])} adapter(s)")
    for adapter_id, adapter_data in state['adapters'].items():
        print(f"   - {adapter_id}:")
        print(f"     Controller MAC: {adapter_data.get('controller_mac', 'N/A')}")
        print(f"     Original MAC: {adapter_data.get('original_mac', 'N/A')}")
        print(f"     Switch addresses: {adapter_data.get('switch_addresses', [])}")
    
    # Get Switch addresses
    print("\n2. Getting Switch addresses...")
    stored_addresses = get_stored_switch_addresses()
    print(f"   Stored addresses: {stored_addresses}")
    
    # Initialize NXBT
    print("\n3. Initializing NXBT...")
    nx = nxbt.Nxbt()
    
    # Get all known Switch addresses
    all_addresses = nx.get_switch_addresses()
    print(f"   All known addresses: {all_addresses}")
    
    if not all_addresses:
        print("   ERROR: No Switch addresses found!")
        print("   Please connect to a Switch first using Change Grip/Order menu.")
        sys.exit(1)
    
    # Attempt reconnection
    print("\n4. Attempting reconnection...")
    print("   Make sure your Switch is:")
    print("   - Powered on")
    print("   - On the Home Screen (NOT Change Grip/Order menu)")
    print("   - Within Bluetooth range")
    print()
    
    try:
        controller_index = nx.create_controller(
            nxbt.PRO_CONTROLLER,
            reconnect_address=all_addresses
        )
        
        print(f"   Controller created with index: {controller_index}")
        
        # Wait for connection
        print("\n5. Waiting for connection...")
        timeout = 30
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            state = nx.state[controller_index]
            current_state = state.get("state", "unknown")
            
            if current_state == "connected":
                print(f"   SUCCESS! Connected to Switch!")
                print(f"   Last connection: {state.get('last_connection', 'N/A')}")
                break
            elif current_state == "crashed":
                print(f"   ERROR: Controller crashed!")
                print(f"   Error: {state.get('errors', 'Unknown error')}")
                sys.exit(1)
            else:
                print(f"   State: {current_state}...", end='\r')
            
            time.sleep(0.5)
        else:
            print(f"\n   TIMEOUT: Connection took too long")
            sys.exit(1)
        
        # Test input
        print("\n6. Testing input (pressing A button)...")
        nx.press_buttons(controller_index, [nxbt.Buttons.A])
        print("   A button pressed!")
        
        time.sleep(1)
        
        # Cleanup
        print("\n7. Cleaning up...")
        nx.remove_controller(controller_index)
        print("   Controller removed.")
        
        print("\n" + "=" * 60)
        print("RECONNECTION TEST PASSED!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n   ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
