#!/usr/bin/env python3
"""
Script that farms XP in Pokemon Legends ZA at Resturant Le Nah
"""

import nxbt

MACRO = """
LOOP 10000000
    ZL 0.3s
    A 0.3s
    A 0.5s
    ZL 0.3s
    Y 0.3s
    0.3s
"""

def main():
    # Initialize NXBT
    nx = nxbt.Nxbt()
    
    # Get available adapters
    adapters = nx.get_available_adapters()
    if not adapters:
        print("No Bluetooth adapters found!")
        return
    
    print(f"Using adapter: {adapters[0]}")
    
    # Create a Pro Controller
    controller_index = nx.create_controller(
        nxbt.PRO_CONTROLLER,
        adapter_path=adapters[0]
    )
    
    print(f"Controller created with index: {controller_index}")
    print("Waiting for connection to Switch...")
    
    # Wait for the controller to connect
    nx.wait_for_connection(controller_index)
    
    print("Connected!")
    input("Navigate to your game, then press Enter to start the macro...")
    
    print("Running macro...")
    
    # Run the macro
    nx.macro(controller_index, MACRO, block=True)
    
    print("Macro complete!")

if __name__ == "__main__":
    main()
