#!/usr/bin/env python3
"""
Helper script to check if the BlueZ agent is properly registered.
Run this to verify the automatic connection setup is working.
"""

import dbus
import sys

def check_agent_status():
    """Check if an agent is registered with BlueZ."""
    try:
        bus = dbus.SystemBus()
        
        # Try to get the agent manager
        agent_manager = dbus.Interface(
            bus.get_object("org.bluez", "/org/bluez"),
            "org.bluez.AgentManager1")
        
        print("✓ BlueZ Agent Manager is accessible")
        
        # Check if our agent path exists
        try:
            agent_obj = bus.get_object("org.bluez", "/nxbt/agent")
            print("✓ NXBT agent is registered at /nxbt/agent")
            return True
        except dbus.exceptions.DBusException:
            print("✗ NXBT agent is not currently registered")
            print("  (This is normal if NXBT is not running)")
            return False
            
    except dbus.exceptions.DBusException as e:
        print(f"✗ Error accessing BlueZ: {e}")
        print("  Make sure BlueZ is running: sudo systemctl status bluetooth")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False

def check_adapter_status():
    """Check Bluetooth adapter status."""
    try:
        bus = dbus.SystemBus()
        
        # Get the default adapter
        manager = dbus.Interface(
            bus.get_object("org.bluez", "/"),
            "org.freedesktop.DBus.ObjectManager")
        
        objects = manager.GetManagedObjects()
        
        adapter_found = False
        for path, interfaces in objects.items():
            if "org.bluez.Adapter1" in interfaces:
                adapter_found = True
                adapter = interfaces["org.bluez.Adapter1"]
                
                print(f"\n✓ Bluetooth Adapter found: {path}")
                print(f"  Address: {adapter.get('Address', 'Unknown')}")
                print(f"  Name: {adapter.get('Name', 'Unknown')}")
                print(f"  Powered: {adapter.get('Powered', False)}")
                print(f"  Discoverable: {adapter.get('Discoverable', False)}")
                print(f"  Pairable: {adapter.get('Pairable', False)}")
                break
        
        if not adapter_found:
            print("✗ No Bluetooth adapter found")
            return False
            
        return True
        
    except Exception as e:
        print(f"✗ Error checking adapter: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("NXBT Automatic Connection Status Check")
    print("=" * 60)
    
    print("\n[1] Checking Bluetooth Adapter...")
    adapter_ok = check_adapter_status()
    
    print("\n[2] Checking BlueZ Agent...")
    agent_ok = check_agent_status()
    
    print("\n" + "=" * 60)
    if adapter_ok:
        print("Status: Ready for automatic connections!")
        print("\nTo test:")
        print("  1. Run: sudo python3 test_auto_connect.py")
        print("  2. Go to Switch 'Change Grip/Order' menu")
        print("  3. Controller should connect automatically")
    else:
        print("Status: Setup incomplete")
        print("\nPlease ensure:")
        print("  - Bluetooth service is running")
        print("  - You have a Bluetooth adapter")
        print("  - You're running as root (sudo)")
    print("=" * 60)
    
    sys.exit(0 if adapter_ok else 1)
