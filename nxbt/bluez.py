import subprocess
import re
import os
import time
import logging
from shutil import which
import random
from pathlib import Path
import json

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop


# Path for storing connection state (MAC addresses, etc.)
NXBT_STATE_DIR = Path.home() / ".nxbt"
NXBT_STATE_FILE = NXBT_STATE_DIR / "connection_state.json"


SERVICE_NAME = "org.bluez"
BLUEZ_OBJECT_PATH = "/org/bluez"
ADAPTER_INTERFACE = SERVICE_NAME + ".Adapter1"
PROFILEMANAGER_INTERFACE = SERVICE_NAME + ".ProfileManager1"
DEVICE_INTERFACE = SERVICE_NAME + ".Device1"
AGENT_INTERFACE = SERVICE_NAME + ".Agent1"
AGENTMANAGER_INTERFACE = SERVICE_NAME + ".AgentManager1"


def find_object_path(bus, service_name, interface_name, object_name=None):
    """Searches for a D-Bus object path that contains a specified interface
    under a specified service.

    :param bus: A DBus object used to access the DBus.
    :type bus: DBus
    :param service_name: The name of a D-Bus service to search for the
    object path under.
    :type service_name: string
    :param interface_name: The name of a D-Bus interface to search for
    within objects under the specified service.
    :type interface_name: string
    :param object_name: The name or ending of the object path,
    defaults to None
    :type object_name: string, optional
    :return: The D-Bus object path or None, if no matching object
    can be found
    :rtype: string
    """

    manager = dbus.Interface(
        bus.get_object(service_name, "/"),
        "org.freedesktop.DBus.ObjectManager")

    # Iterating over objects under the specified service
    # and searching for the specified interface
    for path, ifaces in manager.GetManagedObjects().items():
        managed_interface = ifaces.get(interface_name)
        if managed_interface is None:
            continue
        # If the object name wasn't specified or it matches
        # the interface address or the path ending
        elif (not object_name or
                object_name == managed_interface["Address"] or
                path.endswith(object_name)):
            obj = bus.get_object(service_name, path)
            return dbus.Interface(obj, interface_name).object_path

    return None


def find_objects(bus, service_name, interface_name):
    """Searches for D-Bus objects that contain a specified interface
    under a specified service.

    :param bus: A DBus object used to access the DBus.
    :type bus: DBus
    :param service_name: The name of a D-Bus service to search for the
    object path under.
    :type service_name: string
    :param interface_name: The name of a D-Bus interface to search for
    within objects under the specified service.
    :type interface_name: string
    :return: The D-Bus object paths matching the arguments
    :rtype: array
    """

    manager = dbus.Interface(
        bus.get_object(service_name, "/"),
        "org.freedesktop.DBus.ObjectManager")
    paths = []

    # Iterating over objects under the specified service
    # and searching for the specified interface within them
    for path, ifaces in manager.GetManagedObjects().items():
        managed_interface = ifaces.get(interface_name)
        if managed_interface is None:
            continue
        else:
            obj = bus.get_object(service_name, path)
            path = str(dbus.Interface(obj, interface_name).object_path)
            paths.append(path)

    return paths


def toggle_clean_bluez(toggle):
    """Enables or disables all BlueZ plugins,
    BlueZ compatibility mode, and removes all extraneous
    SDP Services offered.
    Requires root user to be run. The units and Bluetooth
    service will not be restarted if the input plugin
    already matches the toggle.

    :param toggle: A boolean element indicating if BlueZ 
    should be cleaned (True) or not (False)
    :type toggle: boolean
    :raises PermissionError: If the user is not root
    :raises Exception: If the units can't be reloaded
    :raises Exception: If sdptool, hciconfig, or hcitool are not available.
    """

    service_path = "/lib/systemd/system/bluetooth.service"
    override_dir = Path("/run/systemd/system/bluetooth.service.d")
    override_path = override_dir / "nxbt.conf"

    if toggle:
        if override_path.is_file():
            # Override exist, no need to restart bluetooth
            return

        with open(service_path) as f:
            for line in f:
                if line.startswith("ExecStart="):
                    exec_start = line.strip() + " --compat --noplugin=*"
                    break
            else:
                raise Exception("systemd service file doesn't have a ExecStart line")

        override = f"[Service]\nExecStart=\n{exec_start}"

        override_dir.mkdir(parents=True, exist_ok=True)
        with override_path.open("w") as f:
            f.write(override)
    else:
        try:
            os.remove(override_path)
        except FileNotFoundError:
            # Override doesn't exist, no need to restart bluetooth
            return

    # Reload units
    _run_command(["systemctl", "daemon-reload"])

    # Reload the bluetooth service with input disabled
    _run_command(["systemctl", "restart", "bluetooth"])

    # Kill a bit of time here to ensure all services have restarted
    time.sleep(0.5)


def clean_sdp_records():
    """Cleans all SDP Records from BlueZ with sdptool

    :raises Exception: On CLI error or sdptool missing
    """
    # TODO: sdptool is deprecated in BlueZ 5. This should ideally
    # use the DBus API, however, bugs seemingly exist with the
    # UnregisterProfile interface.

    # Check if sdptool is available for use
    if which("sdptool") is None:
        raise Exception("sdptool is not available on this system." +
                        "If you can, please install this tool, as " +
                        "it is required for proper functionality.")

    # Enable Read/Write to the SDP server. This is a remedy for a 
    # compatibility mode bug introduced in later versions of BlueZ 5
    _run_command(["chmod", "777", "/var/run/sdp"])

    # Identify/List all SDP services available with sdptool
    result = _run_command(['sdptool', 'browse', 'local']).stdout.decode('utf-8')
    if result is None or len(result.split('\n\n')) < 1:
        return
    
    # Record all service record handles
    exceptions = ["PnP Information"]
    service_rec_handles = []
    for rec in result.split('\n\n'):
        # Skip if exception is in record
        exception_found = False
        for exception in exceptions:
            if exception in rec:
                exception_found = True
                break
        if exception_found:
            continue

        # Read lines and add Record Handles to the list
        for line in rec.split('\n'):
            if "Service RecHandle" in line:
                service_rec_handles.append(line.split(" ")[2])
    
    # Delete all found service records
    if len(service_rec_handles) > 0:
        for record_handle in service_rec_handles:
            _run_command(['sdptool', 'del', record_handle])


def _run_command(command):
    """Runs a specified command on the shell of the system.
    If the command is run unsuccessfully, an error is raised.
    The command must be in the form of an array with each term
    individually listed. Eg: ["which", "bash"]

    :param command: A list of command terms
    :type command: list
    :raises Exception: On command failure or error
    """
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)

    cmd_err = result.stderr.decode("utf-8").replace("\n", "")
    if cmd_err != "":
        raise Exception(cmd_err)
    
    return result


def get_random_controller_mac():
    """Generates a random Switch-compliant MAC address
    """
    def seg():
        random_number = random.randint(0,255)
        hex_number = str(hex(random_number))
        hex_number = hex_number[2:].upper()
        return str(hex_number)
    
    return f"7C:BB:8A:{seg()}:{seg()}:{seg()}"


def load_connection_state():
    """Loads the saved connection state from disk.
    
    The connection state includes:
    - adapter_mac: The MAC address the adapter was using when connected
    - switch_addresses: List of Switch MAC addresses we've connected to
    - adapter_original_mac: The original MAC address of the adapter
    
    :return: A dictionary containing the connection state, or empty dict if none exists
    :rtype: dict
    """
    try:
        if NXBT_STATE_FILE.exists():
            with open(NXBT_STATE_FILE, 'r') as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logging.getLogger('nxbt').debug(f"Failed to load connection state: {e}")
    return {}


def save_connection_state(state):
    """Saves the connection state to disk.
    
    :param state: A dictionary containing the connection state
    :type state: dict
    """
    try:
        NXBT_STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(NXBT_STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
    except IOError as e:
        logging.getLogger('nxbt').debug(f"Failed to save connection state: {e}")


def update_connection_state(adapter_path, adapter_mac, switch_address, original_mac=None):
    """Updates the connection state with new connection information.
    
    This function is called after a successful connection to store the
    MAC addresses for future reconnection attempts.
    
    :param adapter_path: The D-Bus path of the adapter (e.g., /org/bluez/hci0)
    :type adapter_path: str
    :param adapter_mac: The MAC address the adapter is currently using
    :type adapter_mac: str
    :param switch_address: The MAC address of the connected Switch
    :type switch_address: str
    :param original_mac: The original MAC address of the adapter before any changes
    :type original_mac: str, optional
    """
    state = load_connection_state()
    
    adapter_id = adapter_path.split('/')[-1] if adapter_path else 'unknown'
    
    if 'adapters' not in state:
        state['adapters'] = {}
    
    if adapter_id not in state['adapters']:
        state['adapters'][adapter_id] = {
            'original_mac': original_mac or adapter_mac,
            'controller_mac': adapter_mac,
            'switch_addresses': []
        }
    
    # Update the controller MAC (the MAC we're using to connect)
    state['adapters'][adapter_id]['controller_mac'] = adapter_mac
    
    # Store original MAC if provided and not already set
    if original_mac and not state['adapters'][adapter_id].get('original_mac'):
        state['adapters'][adapter_id]['original_mac'] = original_mac
    
    # Add the Switch address if not already in the list
    if switch_address and switch_address.upper() not in [
            addr.upper() for addr in state['adapters'][adapter_id]['switch_addresses']]:
        state['adapters'][adapter_id]['switch_addresses'].append(switch_address.upper())
    
    save_connection_state(state)
    logging.getLogger('nxbt').debug(
        f"Updated connection state: adapter={adapter_id}, mac={adapter_mac}, switch={switch_address}")


def get_adapter_controller_mac(adapter_path):
    """Gets the stored controller MAC address for an adapter.
    
    This is the MAC address that was used during the last successful
    connection and should be used for reconnection.
    
    :param adapter_path: The D-Bus path of the adapter
    :type adapter_path: str
    :return: The stored controller MAC address, or None if not found
    :rtype: str or None
    """
    state = load_connection_state()
    adapter_id = adapter_path.split('/')[-1] if adapter_path else 'unknown'
    
    if 'adapters' in state and adapter_id in state['adapters']:
        return state['adapters'][adapter_id].get('controller_mac')
    return None


def get_stored_switch_addresses(adapter_path=None):
    """Gets all stored Switch addresses, optionally filtered by adapter.
    
    :param adapter_path: The D-Bus path of the adapter to filter by, or None for all
    :type adapter_path: str, optional
    :return: A list of Switch MAC addresses
    :rtype: list
    """
    state = load_connection_state()
    addresses = []
    
    if 'adapters' not in state:
        return addresses
    
    if adapter_path:
        adapter_id = adapter_path.split('/')[-1]
        if adapter_id in state['adapters']:
            addresses = state['adapters'][adapter_id].get('switch_addresses', [])
    else:
        # Get all addresses from all adapters
        for adapter_data in state['adapters'].values():
            addresses.extend(adapter_data.get('switch_addresses', []))
        # Remove duplicates while preserving order
        addresses = list(dict.fromkeys(addresses))
    
    return addresses


def replace_mac_addresses(adapter_paths, addresses):
    """Replaces a list of adapter's Bluetooth MAC addresses
    with Switch-compliant Controller MAC addresses. If the
    addresses argument is specified, the adapter path's
    MAC addresses will be reset to respective (index-wise)
    address in the list.

    :param adapter_paths: A list of Bluetooth adapter paths
    :type adapter_paths: list
    :param addresses: A list of Bluetooth MAC addresses,
    defaults to False
    :type addresses: bool, optional
    """
    if which("hcitool") is None:
        raise Exception("hcitool is not available on this system." +
                        "If you can, please install this tool, as " +
                        "it is required for proper functionality.")
    if which("hciconfig") is None:
        raise Exception("hciconfig is not available on this system." +
                        "If you can, please install this tool, as " +
                        "it is required for proper functionality.")

    if addresses:
        assert len(addresses) == len(adapter_paths)

    for i in range(len(adapter_paths)):
        adapter_id = adapter_paths[i].split('/')[-1]
        mac = addresses[i].split(':')
        cmds = ['hcitool', '-i', adapter_id, 'cmd', '0x3f', '0x001',
                f'0x{mac[5]}',f'0x{mac[4]}',f'0x{mac[3]}',f'0x{mac[2]}',
                f'0x{mac[1]}',f'0x{mac[0]}']
        _run_command(cmds)
        _run_command(['hciconfig', adapter_id, 'reset'])


def find_devices_by_alias(alias, return_path=False, created_bus=None):
    """Finds the Bluetooth addresses of devices
    that have a specified Bluetooth alias. Aliases
    are converted to uppercase before comparison
    as BlueZ usually converts aliases to uppercase.

    :param address: The Bluetooth MAC address
    :type address: string
    :return: The path to the D-Bus object or None
    :rtype: string or None
    """

    if created_bus is not None:
        bus = created_bus
    else:
        bus = dbus.SystemBus()
    # Find all connected/paired/discovered devices
    devices = find_objects(
        bus,
        SERVICE_NAME,
        DEVICE_INTERFACE)

    addresses = []
    matching_paths = []
    for path in devices:
        # Get the device's address and paired status
        device_props = dbus.Interface(
            bus.get_object(SERVICE_NAME, path),
            "org.freedesktop.DBus.Properties")
        device_alias = device_props.Get(
            DEVICE_INTERFACE,
            "Alias").upper()
        device_addr = device_props.Get(
            DEVICE_INTERFACE,
            "Address").upper()

        # Check for an address match
        if device_alias.upper() == alias.upper():
            addresses.append(device_addr)
            matching_paths.append(path)

    # Close the dbus connection if we created one
    if created_bus is None:
        bus.close()

    if return_path:
        return addresses, matching_paths
    else:
        return addresses


def disconnect_devices_by_alias(alias, created_bus=None):
    """Disconnects all devices matching an alias.

    :param alias: The device's alias
    :type alias: string
    """

    if created_bus is not None:
        bus = created_bus
    else:
        bus = dbus.SystemBus()
    # Find all connected/paired/discovered devices
    devices = find_objects(
        bus,
        SERVICE_NAME,
        DEVICE_INTERFACE)

    addresses = []
    matching_paths = []
    for path in devices:
        # Get the device's address and paired status
        device_props = dbus.Interface(
            bus.get_object(SERVICE_NAME, path),
            "org.freedesktop.DBus.Properties")
        device_alias = device_props.Get(
            DEVICE_INTERFACE,
            "Alias").upper()

        # Check for an alias match
        if device_alias.upper() == alias.upper():
            device = dbus.Interface(
                bus.get_object(SERVICE_NAME, path),
                DEVICE_INTERFACE)
            try:
                device.Disconnect()
            except Exception as e:
                print(e)

    # Close the dbus connection if we created one
    if created_bus is None:
        bus.close()


class AutoAcceptAgent(dbus.service.Object):
    """A DBus Agent that automatically accepts all pairing and authorization requests.
    This is needed to handle incoming connections from the Nintendo Switch without
    requiring manual intervention via bluetoothctl.
    """

    def __init__(self, bus, path):
        super().__init__(bus, path)
        self.logger = logging.getLogger('nxbt')

    @dbus.service.method(AGENT_INTERFACE, in_signature="", out_signature="")
    def Release(self):
        """Called when the agent is unregistered."""
        self.logger.debug("Agent released")

    @dbus.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        """Automatically authorize service requests."""
        self.logger.debug(f"Authorizing service for device {device}")
        return

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        """Return a pin code for pairing."""
        self.logger.debug(f"RequestPinCode for {device}")
        return "0000"

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        """Return a passkey for pairing."""
        self.logger.debug(f"RequestPasskey for {device}")
        return dbus.UInt32(0)

    @dbus.service.method(AGENT_INTERFACE, in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        """Display passkey (no-op for auto-accept)."""
        self.logger.debug(f"DisplayPasskey: {passkey} for {device}")

    @dbus.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        """Display pin code (no-op for auto-accept)."""
        self.logger.debug(f"DisplayPinCode: {pincode} for {device}")

    @dbus.service.method(AGENT_INTERFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        """Automatically confirm pairing requests."""
        self.logger.debug(f"Auto-confirming pairing for {device}")
        return

    @dbus.service.method(AGENT_INTERFACE, in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        """Automatically authorize connection requests."""
        self.logger.debug(f"Auto-authorizing connection for {device}")
        return

    @dbus.service.method(AGENT_INTERFACE, in_signature="", out_signature="")
    def Cancel(self):
        """Handle cancellation of requests."""
        self.logger.debug("Request cancelled")


class BlueZ():
    """Exposes the BlueZ D-Bus API as a Python object.
    """

    def __init__(self, adapter_path="/org/bluez/hci0"):

        self.logger = logging.getLogger('nxbt')

        # Initialize DBus main loop for agent support
        DBusGMainLoop(set_as_default=True)

        self.bus = dbus.SystemBus()
        self.device_path = adapter_path

        # If we weren't able to find an adapter with the specified ID,
        # try to find any usable Bluetooth adapter
        if self.device_path is None:
            self.device_path = find_object_path(
                self.bus,
                SERVICE_NAME,
                ADAPTER_INTERFACE)

        # If we aren't able to find an adapter still
        if self.device_path is None:
            raise Exception("Unable to find a bluetooth adapter")

        # Load the adapter's interface
        self.logger.debug(f"Using adapter under object path: {self.device_path}")
        self.device = dbus.Interface(
            self.bus.get_object(
                SERVICE_NAME,
                self.device_path),
            "org.freedesktop.DBus.Properties")

        self.device_id = self.device_path.split("/")[-1]

        # Load the ProfileManager interface
        self.profile_manager = dbus.Interface(self.bus.get_object(
            SERVICE_NAME, BLUEZ_OBJECT_PATH),
            PROFILEMANAGER_INTERFACE)

        self.adapter = dbus.Interface(
            self.bus.get_object(
                SERVICE_NAME,
                self.device_path),
            ADAPTER_INTERFACE)

        # Store the original MAC address for potential restoration
        self._original_address = self.address
        
        # Register auto-accept agent for handling pairing/authorization
        self.agent = None
        self.agent_path = "/nxbt/agent"
        self._register_agent()

    @property
    def original_address(self):
        """Gets the original Bluetooth MAC address of the adapter.
        
        :return: The original MAC address before any modifications
        :rtype: string
        """
        return self._original_address

    @property
    def address(self):
        """Gets the Bluetooth MAC address of the Bluetooth adapter.

        :return: The Bluetooth Adapter's MAC address
        :rtype: string
        """

        return self.device.Get(ADAPTER_INTERFACE, "Address").upper()

    def set_address(self, mac):
        """Sets the Bluetooth MAC address of the Bluetooth adapter.
        The hciconfig CLI is required for setting the address.
        For changes to apply, the Bluetooth interface needs to be
        restarted.

        :param mac: A Bluetooth MAC address in 
        the form of "XX:XX:XX:XX:XX:XX
        :type mac: str
        :raises PermissionError: On run as non-root user
        :raises Exception: On CLI errors
        """
        if which("hcitool") is None:
            raise Exception("hcitool is not available on this system." +
                            "If you can, please install this tool, as " +
                            "it is required for proper functionality.")
        # Reverse MAC (element position-wise) for use with hcitool
        mac_parts = mac.split(":")
        cmds = ['hcitool', '-i', self.device_id, 'cmd', '0x3f', '0x001',
                f'0x{mac_parts[5]}',f'0x{mac_parts[4]}',f'0x{mac_parts[3]}',f'0x{mac_parts[2]}',
                f'0x{mac_parts[1]}',f'0x{mac_parts[0]}']
        _run_command(cmds)
        _run_command(['hciconfig', self.device_id, 'reset'])
        self.logger.debug(f"Set adapter MAC address to {mac}")

    def prepare_for_reconnect(self, switch_address=None):
        """Prepares the adapter for reconnection by restoring the stored MAC address.
        
        This method checks if we have a stored controller MAC address from a previous
        successful connection and sets the adapter to use that MAC address. This is
        necessary because the Switch remembers the controller's MAC address and will
        only accept reconnections from the same MAC.
        
        :param switch_address: Optional Switch address to look up the specific MAC used
        :type switch_address: str, optional
        :return: True if MAC was restored, False otherwise
        :rtype: bool
        """
        stored_mac = get_adapter_controller_mac(self.device_path)
        
        if stored_mac:
            current_mac = self.address
            if current_mac.upper() != stored_mac.upper():
                self.logger.debug(
                    f"Restoring controller MAC for reconnection: {stored_mac} (current: {current_mac})")
                try:
                    self.set_address(stored_mac)
                    return True
                except Exception as e:
                    self.logger.debug(f"Failed to restore MAC address: {e}")
                    return False
            else:
                self.logger.debug(f"MAC address already matches stored value: {stored_mac}")
                return True
        else:
            self.logger.debug("No stored MAC address found for this adapter")
            return False

    def save_connection_info(self, switch_address):
        """Saves the current connection information for future reconnection.
        
        This should be called after a successful connection to store the
        adapter's MAC address and the Switch's address.
        
        :param switch_address: The MAC address of the connected Switch
        :type switch_address: str
        """
        update_connection_state(
            self.device_path,
            self.address,
            switch_address,
            self._original_address
        )
        self.logger.debug(f"Saved connection info: adapter={self.address}, switch={switch_address}")

    def set_class(self, device_class):
        if which("hciconfig") is None:
            raise Exception("hciconfig is not available on this system." +
                            "If you can, please install this tool, as " +
                            "it is required for proper functionality.")
        _run_command(['hciconfig', self.device_id, 'class', device_class])

    def reset_adapter(self):
        if which("hciconfig") is None:
            raise Exception("hciconfig is not available on this system." +
                            "If you can, please install this tool, as " +
                            "it is required for proper functionality.")
        _run_command(['hciconfig', self.device_id, 'reset'])

    @property
    def name(self):
        """Gets the name of the Bluetooth adapter.

        :return: The name of the Bluetooth adapter.
        :rtype: string
        """

        return self.device.Get(ADAPTER_INTERFACE, "Name")

    @property
    def alias(self):
        """Gets the alias of the Bluetooth adapter. This value is used
        as the "friendly" name of the adapter when communicating over
        Bluetooth.

        :return: The adapter's alias
        :rtype: string
        """

        return self.device.Get(ADAPTER_INTERFACE, "Alias")

    def set_alias(self, value):
        """Asynchronously sets the alias of the Bluetooth adapter.
        If you wish to check the set value, a time delay is needed
        before the alias getter is run.

        :param value: The new value to be set as the adapter's alias
        :type value: string
        """

        self.device.Set(ADAPTER_INTERFACE, "Alias", value)

    @property
    def pairable(self):
        """Gets the pairable status of the Bluetooth adapter.

        :return: A boolean value representing if the adapter is set as
        pairable or not
        :rtype: boolean
        """

        return bool(self.device.Get(ADAPTER_INTERFACE, "Pairable"))

    def set_pairable(self, value):
        """Sets the pariable boolean status of the Bluetooth adapter.

        :param value: A boolean value representing if the adapter is
        pairable or not.
        :type value: boolean
        """

        dbus_value = dbus.Boolean(value)
        self.device.Set(ADAPTER_INTERFACE, "Pairable", dbus_value)

    @property
    def pairable_timeout(self):
        """Gets the timeout time (in seconds) for how long the adapter
        should remain as pairable. Defaults to 0 (no timeout).

        :return: The pairable timeout in seconds
        :rtype: int
        """

        return self.device.Get(ADAPTER_INTERFACE, "PairableTimeout")

    def set_pairable_timeout(self, value):
        """Sets the timeout time (in seconds) for the pairable property.

        :param value: The pairable timeout value in seconds
        :type value: int
        """

        dbus_value = dbus.UInt32(value)
        self.device.Set(ADAPTER_INTERFACE, "PairableTimeout", dbus_value)

    def trust_device(self, device_path):
        """Marks a device as trusted to allow automatic connections.

        :param device_path: The D-Bus path to the device
        :type device_path: string
        """
        try:
            device_props = dbus.Interface(
                self.bus.get_object(SERVICE_NAME, device_path),
                "org.freedesktop.DBus.Properties")
            device_props.Set(DEVICE_INTERFACE, "Trusted", dbus.Boolean(True))
            self.logger.debug(f"Device {device_path} marked as trusted")
        except dbus.exceptions.DBusException as e:
            self.logger.debug(f"Failed to trust device: {e}")

    @property
    def discoverable(self):
        """Gets the discoverable status of the Bluetooth adapter

        :return: The boolean status of the discoverable status
        :rtype: boolean
        """

        return bool(self.device.Get(ADAPTER_INTERFACE, "Discoverable"))

    def set_discoverable(self, value):
        """Sets the discoverable boolean status of the Bluetooth adapter.

        :param value: A boolean value representing if the Bluetooth adapter
        is discoverable or not.
        :type value: boolean
        """

        dbus_value = dbus.Boolean(value)
        self.device.Set(ADAPTER_INTERFACE, "Discoverable", dbus_value)

    @property
    def discoverable_timeout(self):
        """Gets the timeout time (in seconds) for how long the adapter
        should remain as discoverable. Defaults to 180 (3 minutes).

        :return: The discoverable timeout in seconds
        :rtype: int
        """

        return self.device.Get(ADAPTER_INTERFACE, "DiscoverableTimeout")

    def set_discoverable_timeout(self, value):
        """Sets the discoverable time (in seconds) for the discoverable
        property. Setting this property to 0 results in an infinite
        discoverable timeout.

        :param value: The discoverable timeout value in seconds
        :type value: int
        """

        dbus_value = dbus.UInt32(value)
        self.device.Set(
            ADAPTER_INTERFACE,
            "DiscoverableTimeout",
            dbus_value)

    @property
    def device_class(self):
        """Gets the Bluetooth class of the device. This represents what type
        of device this reporting as (Ex: Gamepad, Headphones, etc).

        :return: A 32-bit hexadecimal Integer representing the
        Bluetooth Code for a given device type.
        :rtype: string
        """

        # This is another hacky bit. We're using hciconfig here instead
        # of the D-Bus API so that results match the setter. See the
        # setter for further justification on using hciconfig.
        result = subprocess.run(
            ["hciconfig", self.device_id, "class"],
            stdout=subprocess.PIPE)
        device_class = result.stdout.decode("utf-8").split("Class: ")[1][0:8]

        return device_class

    def set_device_class(self, device_class):
        """Sets the Bluetooth class of the device. This represents what type
        of device this reporting as (Ex: Gamepad, Headphones, etc).
        Note: To work this function *MUST* be run as the super user. An
        exception is returned if this function is run without elevation.

        :param device_class: A 32-bit Hexadecimal integer
        :type device_class: string
        :raises PermissionError: If user is not root
        :raises ValueError: If the device class is not length 8
        :raises Exception: On inability to set class
        """

        if os.geteuid() != 0:
            raise PermissionError("The device class must be set as root")

        if len(device_class) != 8:
            raise ValueError("Device class must be length 8")

        # This is a bit of a hack. BlueZ allows you to set this value, however,
        # a config file needs to filled and the BT daemon restarted. This is a
        # good compromise but requires super user privileges. Not ideal.
        result = subprocess.run(
            ["hciconfig", self.device_id, "class", device_class],
            stderr=subprocess.PIPE)

        # Checking if there was a problem setting the device class
        cmd_err = result.stderr.decode("utf-8").replace("\n", "")
        if cmd_err != "":
            raise Exception(cmd_err)

    @property
    def powered(self):
        """The powered state of the adapter (on/off) as a boolean value.

        :return: A boolean representing the powered state of the adapter.
        :rtype: boolean
        """

        return bool(self.device.Get(ADAPTER_INTERFACE, "Powered"))

    def set_powered(self, value):
        """Switches the adapter on or off.

        :param value: A boolean value switching the adapter on or off
        :type value: boolean
        """

        dbus_value = dbus.Boolean(value)
        self.device.Set(ADAPTER_INTERFACE, "Powered", dbus_value)

    def register_profile(self, profile_path, uuid, opts):
        """Registers an SDP record on the BlueZ SDP server.

        Options (non-exhaustive, refer to BlueZ docs for
        the complete list):

        - Name: Human readable name of the profile

        - Role: Specifies precise local role. Either "client"
        or "servier".

        - RequireAuthentication: A boolean value indicating if
        pairing is required before connection.

        - RequireAuthorization: A boolean value indiciating if
        authorization is needed before connection.

        - AutoConnect: A boolean value indicating whether a
        connection can be forced if a client UUID is present.

        - ServiceRecord: An XML SDP record as a string.

        :param profile_path: The path for the SDP record
        :type profile_path: string
        :param uuid: The UUID for the SDP record
        :type uuid: string
        :param opts: The options for the SDP server
        :type opts: dict
        """

        return self.profile_manager.RegisterProfile(profile_path, uuid, opts)

    def unregister_profile(self, profile):
        """Unregisters a given SDP record from the BlueZ SDP server.

        :param profile: A SDP record profile object
        :type profile: Profile
        """

        self.profile_manager.UnregisterProfile(profile)

    def _register_agent(self):
        """Registers an auto-accept agent to handle pairing and authorization requests."""
        try:
            # Create and register the agent
            self.agent = AutoAcceptAgent(self.bus, self.agent_path)
            
            # Get the agent manager
            agent_manager = dbus.Interface(
                self.bus.get_object(SERVICE_NAME, "/org/bluez"),
                AGENTMANAGER_INTERFACE)
            
            # Register the agent with NoInputNoOutput capability
            agent_manager.RegisterAgent(self.agent_path, "NoInputNoOutput")
            
            # Request to make this the default agent
            agent_manager.RequestDefaultAgent(self.agent_path)
            
            self.logger.debug("Auto-accept agent registered successfully")
        except dbus.exceptions.DBusException as e:
            # Agent might already be registered, which is fine
            self.logger.debug(f"Agent registration: {e}")

    def _unregister_agent(self):
        """Unregisters the auto-accept agent."""
        if self.agent:
            try:
                agent_manager = dbus.Interface(
                    self.bus.get_object(SERVICE_NAME, "/org/bluez"),
                    AGENTMANAGER_INTERFACE)
                agent_manager.UnregisterAgent(self.agent_path)
                self.logger.debug("Agent unregistered")
            except dbus.exceptions.DBusException as e:
                self.logger.debug(f"Agent unregistration: {e}")
            finally:
                self.agent = None

    def reset(self):
        """Restarts the Bluetooth Service

        :raises Exception: If the bluetooth service can't be restarted
        """

        # Unregister agent before restart
        self._unregister_agent()

        result = subprocess.run(
            ["systemctl", "restart", "bluetooth"],
            stderr=subprocess.PIPE)

        cmd_err = result.stderr.decode("utf-8").replace("\n", "")
        if cmd_err != "":
            raise Exception(cmd_err)

        self.device = dbus.Interface(
            self.bus.get_object(
                SERVICE_NAME,
                self.device_path),
            "org.freedesktop.DBus.Properties")
        self.profile_manager = dbus.Interface(
            self.bus.get_object(
                SERVICE_NAME,
                BLUEZ_OBJECT_PATH),
            PROFILEMANAGER_INTERFACE)

        # Re-register agent after restart
        self._register_agent()

    def get_discovered_devices(self):
        """Gets a dict of all discovered (or previously discovered
        and connected) devices. The key is the device's dbus object
        path and the values are the device's properties.

        The following is a non-exhaustive list of the properties a
        device dictionary can contain:
        - "Address": The Bluetooth address
        - "Alias": The friendly name of the device
        - "Paired": Whether the device is paired
        - "Connected": Whether the device is presently connected
        - "UUIDs": The services a device provides

        :return: A dictionary of all discovered devices
        :rtype: dictionary
        """

        bluez_objects = dbus.Interface(
            self.bus.get_object(SERVICE_NAME, "/"),
            "org.freedesktop.DBus.ObjectManager")

        devices = {}
        objects = bluez_objects.GetManagedObjects()
        for path, interfaces in list(objects.items()):
            if DEVICE_INTERFACE in interfaces:
                devices[str(path)] = interfaces[DEVICE_INTERFACE]

        return devices

    def discover_devices(self, alias=None, timeout=10, callback=None):
        """Runs a device discovery of the timeout length (in seconds)
        on the adapter. If specified, a callback is run, every second,
        and passed an updated list of discovered devices. An alias
        can be specified to filter discovered devices.

        The following is a non-exhaustive list of the properties a
        device dictionary can contain:
        - "Address": The Bluetooth address
        - "Alias": The friendly name of the device
        - "Paired": Whether the device is paired
        - "Connected": Whether the device is presently connected
        - "UUIDs": The services a device provides

        :param alias: The alias of a bluetooth device, defaults to None
        :type alias: string, optional
        :param timeout: The discovery timeout in seconds, defaults to 10
        :type timeout: int, optional
        :param callback: A callback function, defaults to None
        :type callback: function, optional
        :return: A dictionary of discovered devices with the object path
        as the key and the device properties as the dictionary properties
        :rtype: dictionary
        """

        # TODO: Device discovery still needs work. Currently, devices
        # are added as DBus objects while device discovery runs, however,
        # added devices linger after discovery stops. This means a device
        # can become unpairable, still show up on a new discovery session,
        # and throw an error when an attempt is made to pair it. Using DBus
        # signals ("interface added"/"property changed") does not solve
        # this issue.

        # Get all devices that have been previously discovered
        devices = self.get_discovered_devices()

        # Start discovering new devices and loop
        self.set_powered(True)
        self.set_pairable(True)
        self.adapter.StartDiscovery()
        try:
            for i in range(0, timeout):
                time.sleep(1)

                new_devices = self.get_discovered_devices()
                # Shallowly merging dictionaries. Latter dictionary
                # overrides the former. Requires Python 3.5
                devices = {**devices, **new_devices}

                if callback:
                    callback(devices)
        finally:
            self.adapter.StopDiscovery()
            time.sleep(1)

        # Filter out paired devices or devices that don't
        # match a specified alias.
        filtered_devices = {}
        for key in devices.keys():
            # Filter for devices matching alias, if specified
            if "Alias" not in devices[key].keys():
                continue
            if alias and not alias == devices[key]["Alias"]:
                continue

            # Filter for paired devices
            if "Paired" not in devices[key].keys():
                continue
            if devices[key]["Paired"]:
                continue

            filtered_devices[key] = devices[key]

        return filtered_devices

    def pair_device(self, device_path):
        """Pairs a discovered device at a given DBus object path.

        :param device_path: The D-Bus object path to the device
        :type device_path: string
        """

        device = dbus.Interface(
            self.bus.get_object(
                SERVICE_NAME,
                device_path),
            DEVICE_INTERFACE)
        device.Pair()

    def connect_device(self, device_path):

        device = dbus.Interface(
            self.bus.get_object(
                SERVICE_NAME,
                device_path),
            DEVICE_INTERFACE)
        try:
            device.Connect()
        except dbus.exceptions.DBusException as e:
            self.logger.exception(e)

    def remove_device(self, path):
        """Removes a device that's been either discovered, paired,
        connected, etc.

        :param path: The D-Bus path to the object
        :type path: string
        """

        self.adapter.RemoveDevice(
            self.bus.get_object(SERVICE_NAME, path))

    def find_device_by_address(self, address):
        """Finds the D-Bus path to a device that contains the
        specified address.

        :param address: The Bluetooth MAC address
        :type address: string
        :return: The path to the D-Bus object or None
        :rtype: string or None
        """

        # Find all connected/paired/discovered devices
        devices = find_objects(
            self.bus,
            SERVICE_NAME,
            DEVICE_INTERFACE)
        for path in devices:
            # Get the device's address and paired status
            device_props = dbus.Interface(
                self.bus.get_object(SERVICE_NAME, path),
                "org.freedesktop.DBus.Properties")
            device_addr = device_props.Get(
                DEVICE_INTERFACE,
                "Address").upper()

            # Check for an address match
            if device_addr != address.upper():
                continue
            return path

        return None
    
    def find_connected_devices(self, alias_filter=False):
        """Finds the D-Bus path to a device that contains the
        specified address.

        :param address: The Bluetooth MAC address
        :type address: string
        :return: The path to the D-Bus object or None
        :rtype: string or None
        """

        devices = find_objects(
            self.bus,
            SERVICE_NAME,
            DEVICE_INTERFACE)
        conn_devices = []
        for path in devices:
            # Get the device's connection status
            device_props = dbus.Interface(
                self.bus.get_object(SERVICE_NAME, path),
                "org.freedesktop.DBus.Properties")
            device_conn_status = device_props.Get(
                DEVICE_INTERFACE,
                "Connected")
            device_alias = device_props.Get(
                DEVICE_INTERFACE,
                "Alias").upper()

            if device_conn_status:
                if alias_filter and device_alias == alias_filter.upper():
                    conn_devices.append(path)
                else:
                    conn_devices.append(path)

        return conn_devices

    def close(self):
        """Cleanup method to unregister agent and close bus connection."""
        self._unregister_agent()
        if hasattr(self, 'bus') and self.bus:
            self.bus.close()
