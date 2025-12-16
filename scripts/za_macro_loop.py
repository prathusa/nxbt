#!/usr/bin/env python3
"""
Script that farms XP in Pokemon Legends ZA at Restaurant Le Nah
Uses Python API for precise button control - holds ZL while pressing A and Y
"""

import nxbt
import time
from tqdm import tqdm

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
    
    try:
        for _ in tqdm(range(10000000), desc="Farming XP", unit="loop"):
            # Hold ZL + press A
            nx.press_buttons(controller_index, [nxbt.Buttons.ZL, nxbt.Buttons.A], down=0.5, up=0.1, block=True)
            
            # Hold ZL + press Y
            nx.press_buttons(controller_index, [nxbt.Buttons.ZL, nxbt.Buttons.Y], down=0.5, up=0.1, block=True)
            
            # Small delay before next loop
            time.sleep(0.5)
                
    except KeyboardInterrupt:
        print("\nMacro stopped by user")
    
    print("Macro complete!")

if __name__ == "__main__":
    main()
