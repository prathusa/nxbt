# Connection Flow Comparison

## Before Fix (Manual Process)

```
┌─────────────────┐
│  Start NXBT     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Make Adapter    │
│ Discoverable    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Switch Finds    │
│ Controller      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Switch Requests │
│ Authorization   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ❌ NO AGENT     │
│ Request Timeout │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ⚠️  MANUAL      │
│ bluetoothctl    │
│ Required        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ User Manually   │
│ Authorizes      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ✓ Connected     │
└─────────────────┘
```

## After Fix (Automatic Process)

```
┌─────────────────┐
│  Start NXBT     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ✓ Auto-Register │
│ DBus Agent      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Make Adapter    │
│ Discoverable    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Switch Finds    │
│ Controller      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Switch Requests │
│ Authorization   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ✓ Agent Auto-   │
│ Approves        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ✓ Device Marked │
│ as Trusted      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ✓ Connected     │
│ Automatically!  │
└─────────────────┘
```

## Key Differences

| Aspect | Before | After |
|--------|--------|-------|
| **Agent** | ❌ Not registered | ✓ Auto-registered |
| **Authorization** | ⚠️ Manual via bluetoothctl | ✓ Automatic |
| **User Action** | Required | None |
| **Reliability** | Timing-dependent | Consistent |
| **Trust** | Not set | ✓ Auto-set |
| **Future Connections** | Same manual process | ✓ Instant |

## Technical Flow

### Agent Registration (New)
```
NXBT Init
    │
    ├─> Create BlueZ instance
    │       │
    │       ├─> Initialize DBusGMainLoop
    │       │
    │       └─> Register AutoAcceptAgent
    │               │
    │               ├─> Set capability: "NoInputNoOutput"
    │               │
    │               └─> Request default agent status
    │
    └─> Ready for connections
```

### Connection Handling (New)
```
Switch Connects
    │
    ├─> BlueZ receives connection request
    │       │
    │       └─> Calls Agent.RequestAuthorization()
    │               │
    │               └─> Agent returns immediately (auto-approve)
    │
    ├─> Connection established
    │       │
    │       └─> Get Switch device path
    │               │
    │               └─> Call trust_device()
    │
    └─> Device trusted for future connections
```

## Agent Methods Called

During a typical connection, these agent methods are invoked:

1. **RequestAuthorization(device)**
   - Called when Switch requests to connect
   - Returns immediately (auto-approve)

2. **AuthorizeService(device, uuid)**
   - Called for HID service authorization
   - Returns immediately (auto-approve)

3. **RequestConfirmation(device, passkey)** (if needed)
   - Called for pairing confirmation
   - Returns immediately (auto-confirm)

## Cleanup Flow

```
NXBT Shutdown
    │
    ├─> Unregister agent
    │       │
    │       └─> Call AgentManager.UnregisterAgent()
    │
    ├─> Close DBus connection
    │
    └─> Exit cleanly
```

## Error Handling

### Agent Already Registered
```
Try: Register agent
    │
    ├─> DBusException: Already registered
    │       │
    │       └─> Log and continue (not fatal)
    │
    └─> Continue with existing agent
```

### Connection Lost
```
Connection Error
    │
    ├─> Attempt reconnection
    │       │
    │       ├─> Agent still registered
    │       │
    │       └─> Auto-approve on reconnect
    │
    └─> Seamless recovery
```

## Benefits Visualization

```
Manual Process:
[Start] ──> [Wait] ──> [Manual Action] ──> [Connected]
         30s         User Required        Total: 30s+

Automatic Process:
[Start] ──────────────────────────────> [Connected]
                                         Total: <5s
```

## State Diagram

```
                    ┌──────────────┐
                    │  NXBT Start  │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Agent Ready  │◄────┐
                    └──────┬───────┘     │
                           │             │
                           ▼             │
                    ┌──────────────┐    │
                    │ Discoverable │    │
                    └──────┬───────┘    │
                           │             │
                           ▼             │
                    ┌──────────────┐    │
                    │   Waiting    │    │
                    └──────┬───────┘    │
                           │             │
                           ▼             │
                    ┌──────────────┐    │
                    │  Connected   │    │
                    └──────┬───────┘    │
                           │             │
                           ▼             │
                    ┌──────────────┐    │
                    │   Trusted    │    │
                    └──────┬───────┘    │
                           │             │
                           ▼             │
                    ┌──────────────┐    │
                    │    Active    │────┘
                    └──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   Cleanup    │
                    └──────────────┘
```
