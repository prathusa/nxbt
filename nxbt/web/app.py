import json
import os
from threading import RLock
import time
from socket import gethostname

from .cert import generate_cert
from ..nxbt import Nxbt, PRO_CONTROLLER
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler


app = Flask(__name__,
            static_url_path='',
            static_folder='static',)

# Initialize nxbt as None - will be created on first use
nxbt = None
nxbt_lock = RLock()
nxbt_init_failed = False
nxbt_restart_count = 0
MAX_NXBT_RESTARTS = 3

def reset_nxbt():
    """Reset the NXBT instance (for recovery from crashes)"""
    global nxbt, nxbt_init_failed, nxbt_restart_count
    
    with nxbt_lock:
        if nxbt is not None:
            try:
                # Try to cleanup the old instance
                nxbt._on_exit()
            except Exception as e:
                print(f"Error during NXBT cleanup: {e}")
        
        nxbt = None
        nxbt_init_failed = False
        nxbt_restart_count += 1
        
        if nxbt_restart_count > MAX_NXBT_RESTARTS:
            print(f"ERROR: NXBT has been restarted {MAX_NXBT_RESTARTS} times. Manual intervention required.")
            nxbt_init_failed = True
            raise RuntimeError("NXBT restart limit exceeded")

def get_nxbt():
    """Get or create the Nxbt instance with proper error handling"""
    global nxbt, nxbt_init_failed
    
    if nxbt_init_failed:
        raise RuntimeError("NXBT initialization previously failed - restart the webapp to retry")
    
    with nxbt_lock:
        if nxbt is None:
            try:
                print("Initializing NXBT manager...")
                nxbt = Nxbt()
                print("NXBT manager initialized successfully")
            except FileNotFoundError as e:
                nxbt_init_failed = True
                print(f"ERROR: Failed to initialize NXBT - multiprocessing manager socket error: {e}")
                print("This usually means:")
                print("  1. The /tmp directory has permission issues")
                print("  2. The /tmp directory is full")
                print("  3. There's a stale socket file from a previous crash")
                print("\nTry running: sudo rm -f /tmp/pymp-* && sudo chmod 1777 /tmp")
                raise
            except Exception as e:
                nxbt_init_failed = True
                print(f"ERROR: Failed to initialize NXBT: {e}")
                raise
        return nxbt

def check_nxbt_alive():
    """Check if NXBT manager is still alive and responsive"""
    global nxbt
    
    if nxbt is None:
        return False
    
    try:
        # Try to access the state - this will fail if manager is dead
        _ = nxbt.state.copy()
        return True
    except (FileNotFoundError, EOFError, ConnectionRefusedError, BrokenPipeError, OSError):
        return False
    except Exception:
        return False

# Configuring/retrieving secret key
secrets_path = os.path.join(
    os.path.dirname(__file__), "secrets.txt"
)
if not os.path.isfile(secrets_path):
    secret_key = os.urandom(24).hex()
    with open(secrets_path, "w") as f:
        f.write(secret_key)
else:
    secret_key = None
    with open(secrets_path, "r") as f:
        secret_key = f.read()
app.config['SECRET_KEY'] = secret_key

# Starting socket server with Flask app
# Explicitly use gevent async mode to match the pywsgi server
sio = SocketIO(app, cookie=False, async_mode='gevent')

user_info_lock = RLock()
USER_INFO = {}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/health')
def health():
    """Health check endpoint to verify NXBT is initialized"""
    global nxbt, nxbt_init_failed
    
    if nxbt_init_failed:
        return {'status': 'error', 'message': 'NXBT initialization failed'}, 500
    
    try:
        nx = get_nxbt()
        return {'status': 'ok', 'adapters': len(nx.get_available_adapters())}, 200
    except Exception as e:
        return {'status': 'error', 'message': str(e)}, 500


@sio.on('connect')
def on_connect():
    with user_info_lock:
        USER_INFO[request.sid] = {}


@sio.on('state')
def on_state():
    try:
        # Check if manager is alive first
        if not check_nxbt_alive():
            print("NXBT manager connection lost - attempting recovery...")
            try:
                reset_nxbt()
                nx = get_nxbt()
                emit('manager_reconnected', {'message': 'NXBT manager reconnected'})
            except Exception as e:
                print(f"Failed to recover NXBT manager: {e}")
                emit('manager_dead', {'error': str(e)})
                return
        
        nx = get_nxbt()
        state_proxy = nx.state.copy()
        state = {}
        for controller in state_proxy.keys():
            state[controller] = state_proxy[controller].copy()
        emit('state', state)
    except (FileNotFoundError, EOFError, ConnectionRefusedError, BrokenPipeError, OSError) as e:
        # Multiprocessing manager has died - attempt recovery
        print(f"NXBT manager connection lost: {e}")
        try:
            reset_nxbt()
            emit('manager_reconnected', {'message': 'NXBT manager reconnected - please recreate controllers'})
        except Exception as recovery_error:
            print(f"Failed to recover NXBT manager: {recovery_error}")
            emit('manager_dead', {'error': str(recovery_error)})
    except Exception as e:
        print(f"Error getting state: {e}")
        emit('state', {})


@sio.on('disconnect')
def on_disconnect():
    print("Disconnected")
    with user_info_lock:
        try:
            if not check_nxbt_alive():
                print("NXBT manager not alive during disconnect - skipping controller cleanup")
                USER_INFO.pop(request.sid, None)
                return
            
            nx = get_nxbt()
            index = USER_INFO[request.sid]["controller_index"]
            nx.remove_controller(index)
        except (KeyError, ValueError):
            pass
        except Exception as e:
            print(f"Error during disconnect cleanup: {e}")
        finally:
            # Clean up user info regardless
            USER_INFO.pop(request.sid, None)


@sio.on('shutdown')
def on_shutdown(index):
    try:
        if not check_nxbt_alive():
            emit('error', 'NXBT manager connection lost')
            return
        
        nx = get_nxbt()
        nx.remove_controller(index)
        # Clean up user info if this was their controller
        with user_info_lock:
            if request.sid in USER_INFO and USER_INFO[request.sid].get("controller_index") == index:
                USER_INFO[request.sid].pop("controller_index", None)
    except ValueError as e:
        emit('error', f'Shutdown error: {str(e)}')
    except Exception as e:
        emit('error', f'Unexpected shutdown error: {str(e)}')


@sio.on('check_controller_health')
def check_controller_health(index):
    """Check if a controller is healthy and return its state"""
    try:
        if not check_nxbt_alive():
            emit('controller_health', {'index': index, 'state': 'manager_dead', 'exists': False})
            return
        
        nx = get_nxbt()
        if index in nx.state:
            state = nx.state[index].get('state')
            emit('controller_health', {'index': index, 'state': state, 'exists': True})
        else:
            emit('controller_health', {'index': index, 'state': None, 'exists': False})
    except (FileNotFoundError, EOFError, ConnectionRefusedError, BrokenPipeError, OSError):
        # Manager died - controller doesn't exist
        emit('controller_health', {'index': index, 'state': 'manager_dead', 'exists': False})
    except Exception as e:
        emit('error', f'Health check error: {str(e)}')


@sio.on('web_create_pro_controller')
def on_create_controller():
    print("Create Controller")

    try:
        if not check_nxbt_alive():
            print("NXBT manager not alive - attempting recovery...")
            reset_nxbt()
        
        nx = get_nxbt()
        
        # Clean up any existing crashed controller for this session
        with user_info_lock:
            if request.sid in USER_INFO and "controller_index" in USER_INFO[request.sid]:
                old_index = USER_INFO[request.sid]["controller_index"]
                try:
                    nx.remove_controller(old_index)
                except (ValueError, KeyError):
                    pass
        
        reconnect_addresses = nx.get_switch_addresses()
        index = nx.create_controller(PRO_CONTROLLER, reconnect_address=reconnect_addresses)

        with user_info_lock:
            USER_INFO[request.sid]["controller_index"] = index

        emit('create_pro_controller', index)
    except Exception as e:
        emit('error', str(e))


@sio.on('web_reconnect_controller')
def on_reconnect_controller():
    """Seamlessly reconnect the controller without going through pairing"""
    print("Reconnect Controller")

    try:
        if not check_nxbt_alive():
            print("NXBT manager not alive - attempting recovery...")
            reset_nxbt()
        
        nx = get_nxbt()
        
        # Remove the old controller
        with user_info_lock:
            if request.sid in USER_INFO and "controller_index" in USER_INFO[request.sid]:
                old_index = USER_INFO[request.sid]["controller_index"]
                try:
                    nx.remove_controller(old_index)
                except (ValueError, KeyError):
                    pass
        
        # Create new controller with reconnect address (seamless reconnection)
        reconnect_addresses = nx.get_switch_addresses()
        if not reconnect_addresses:
            emit('error', 'No Switch addresses found. Please pair first using "Create Controller".')
            return
            
        index = nx.create_controller(PRO_CONTROLLER, reconnect_address=reconnect_addresses)

        with user_info_lock:
            USER_INFO[request.sid]["controller_index"] = index

        emit('reconnect_controller', index)
    except Exception as e:
        emit('error', str(e))


@sio.on('input')
def handle_input(message):
    # print("Webapp Input", time.perf_counter())
    try:
        if not check_nxbt_alive():
            # Silently ignore input if manager is dead
            return
        
        nx = get_nxbt()
        message = json.loads(message)
        index = message[0]
        input_packet = message[1]
        
        # Check if controller exists and is not crashed
        if index in nx.state:
            controller_state = nx.state[index].get('state')
            if controller_state == 'crashed':
                emit('controller_crashed', index)
                return
        
        nx.set_controller_input(index, input_packet)
    except (FileNotFoundError, EOFError, ConnectionRefusedError, BrokenPipeError, OSError):
        # Manager died - silently ignore input
        pass
    except ValueError as e:
        emit('controller_error', {'index': message[0] if message else None, 'error': str(e)})
    except Exception as e:
        emit('error', f'Input error: {str(e)}')


@sio.on('macro')
def handle_macro(message):
    try:
        if not check_nxbt_alive():
            emit('controller_error', {'index': None, 'error': 'NXBT manager connection lost'})
            return
        
        nx = get_nxbt()
        message = json.loads(message)
        index = message[0]
        macro = message[1]
        
        # Check if controller exists and is not crashed
        if index in nx.state:
            controller_state = nx.state[index].get('state')
            if controller_state == 'crashed':
                emit('controller_crashed', index)
                return
        
        nx.macro(index, macro)
    except (FileNotFoundError, EOFError, ConnectionRefusedError, BrokenPipeError, OSError):
        # Manager died - emit error
        emit('controller_error', {'index': message[0] if message else None, 'error': 'NXBT manager connection lost'})
    except ValueError as e:
        emit('controller_error', {'index': message[0] if message else None, 'error': str(e)})
    except Exception as e:
        emit('error', f'Macro error: {str(e)}')


@sio.on('reset_manager')
def on_reset_manager():
    """Manually reset the NXBT manager (for recovery)"""
    try:
        print("Manual NXBT manager reset requested")
        reset_nxbt()
        nx = get_nxbt()
        emit('manager_reset', {'message': 'NXBT manager reset successfully'})
    except Exception as e:
        emit('error', f'Failed to reset manager: {str(e)}')


def start_web_app(ip='0.0.0.0', port=8000, usessl=False, cert_path=None):
    if usessl:
        if cert_path is None:
            # Store certs in the package directory
            cert_path = os.path.join(
                os.path.dirname(__file__), "cert.pem"
            )
            key_path = os.path.join(
                os.path.dirname(__file__), "key.pem"
            )
        else:
            # If specified, store certs at the user's preferred location
            cert_path = os.path.join(
                cert_path, "cert.pem"
            )
            key_path = os.path.join(
                cert_path, "key.pem"
            )
        if not os.path.isfile(cert_path) or not os.path.isfile(key_path):
            print(
                "\n"
                "-----------------------------------------\n"
                "---------------->WARNING<----------------\n"
                "The NXBT webapp is being run with self-\n"
                "signed SSL certificates for use on your\n"
                "local network.\n"
                "\n"
                "These certificates ARE NOT safe for\n"
                "production use. Please generate valid\n"
                "SSL certificates if you plan on using the\n"
                "NXBT webapp anywhere other than your own\n"
                "network.\n"
                "-----------------------------------------\n"
                "\n"
                "The above warning will only be shown once\n"
                "on certificate generation."
                "\n"
            )
            print("Generating certificates...")
            cert, key = generate_cert(gethostname())
            with open(cert_path, "wb") as f:
                f.write(cert)
            with open(key_path, "wb") as f:
                f.write(key)

        server = pywsgi.WSGIServer((ip, port), app, 
                                    handler_class=WebSocketHandler,
                                    keyfile=key_path, 
                                    certfile=cert_path)
        server.serve_forever()
    else:
        server = pywsgi.WSGIServer((ip, port), app, 
                                    handler_class=WebSocketHandler)
        server.serve_forever()


if __name__ == "__main__":
    start_web_app()
