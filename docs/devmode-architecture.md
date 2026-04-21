# How FLT DevMode Actually Works

> *You don't need to read this to use edog. But when the relay drops at 2am and you're staring at logs wondering why your FLT service went dark — you'll be glad you did.*

## The One-Sentence Version

Your local FLT service (`Microsoft.LiveTable.Service`) registers itself with the MWC cloud via an **Azure Relay** — there's no direct HTTP, no port forwarding, no tunneling. The relay IS the tunnel. edog handles everything before and after that relay connection: auth, config, patching, launching, monitoring.

---

## Non-DevMode: How FLT Normally Runs

In a regular deployment, the FLT lifecycle is fully cloud-managed:

1. The FLT service executable gets pushed to an MWC-owned storage account during deployment
2. The **Orchestrator** process on a Backend node downloads and starts it
3. When requests hit **Frontend Service** for FLT, Frontend proxies them to the service's HTTP endpoints (e.g., `LiveTableController`, `LiveTableSchedulerRunController`)

```
User → Frontend Service → Backend Service → FLT Service (running on Backend node)
```

You deploy, Orchestrator runs it, traffic flows through MWC's internal network. No local machine involved.

---

## DevMode: The Azure Relay Architecture

DevMode flips the script. Orchestrator doesn't start FLT — **you do**, on your own machine via `dotnet run` from `Service/Microsoft.LiveTable.Service.EntryPoint`. But the cloud still needs to reach you. That's where Azure Relay comes in.

### Registration Flow

1. **FLT service** (via WCL SDK) calls **Frontend Service** to register itself for a specific capacity
2. **Frontend Service** proxies the registration to **Backend Service**
3. **Backend Service** creates a new relay inside an **Azure Relay Namespace** and starts listening
4. Relay details flow back: Backend → Frontend → Your FLT service
5. **FLT service** starts listening on the relay and initializes the workload context

### What Happens After Registration

Two things run continuously:

- **Health checks** — bidirectional. Backend pings FLT through the relay, FLT pings Backend. If either side goes silent, things break.
- **User traffic** — `User → Frontend → Backend → Azure Relay → Your local FLT`. When FLT needs platform info, it calls Backend back through the same relay.

### The Key Insight

There is **no localhost port being exposed to the internet**. FLT doesn't bind to `localhost:5000` and wait for inbound connections. Instead, the WCL SDK opens an **outbound** connection to Azure Relay and listens there. The cloud reaches you through the relay, not by connecting to your machine directly.

This is why Dev Tunnels / ngrok / port forwarding are all irrelevant here — the platform already solved the "cloud can't reach localhost" problem with Azure Relay.

---

## What edog Does (And What It Doesn't)

edog **does not touch the relay** — the WCL SDK inside FLT handles all relay communication. edog is the setup and lifecycle layer that makes everything else painless:

### 1. Silent CBA Authentication
edog discovers your CBA certificate (e.g., `Admin1CBA.PPE.ccsctp.net`) from `Cert:\CurrentUser\My` and acquires two tokens silently — zero browser popups:

- **Bearer token** (audience: PowerBI API) → written to a live token file → FLT's C# code reads it to POST `/generatemwctoken` → generates MWC tokens at runtime
- **UserAuthorizationToken** (audience: `MwcFrontendBaseEndpoint`) → injected into `workload-dev-mode.json` → WCL SDK skips browser popup

### 2. Config Generation
edog auto-creates `workload-dev-mode.json` in the FLT EntryPoint directory:

```json
{
    "TenantGuid": "<extracted from JWT 'tid' claim>",
    "CapacityGuid": "<from edog-config.json>",
    "MwcFrontendBaseEndpoint": "https://edog.pbidedicated.windows-int.net:443/",
    "WorkloadStartUpMode": "DevMode",
    "EnvironmentType": "PPE",
    "UserAuthorizationToken": "<auto-injected by edog>"
}
```

When the WCL SDK sees `"WorkloadStartUpMode": "DevMode"`, it skips waiting for Orchestrator and uses the endpoint + capacity info to self-register with the relay. `UserAuthorizationToken` prevents the browser popup that WCL would normally show.

edog also ensures `launchSettings.json` has the `-DevMode:LocalConfigFilePath` argument pointing to this file.

### 3. Source Code Patching
edog patches FLT source files in-memory before build — injecting tokens and config into:
- `Service/Microsoft.LiveTable.Service/Controllers/LiveTableController.cs`
- `Service/Microsoft.LiveTable.Service/SparkHttp/GTSBasedSparkClient.cs`
- `Service/Microsoft.LiveTable.Service/WorkloadApp.cs`
- `Service/Microsoft.LiveTable.Service.EntryPoint/Program.cs`
- And others as needed

All patches are tracked via a `.patch` file so they can be cleanly reverted on shutdown (or detected as stale on next startup if edog crashed).

### 4. Build & Launch
edog runs `dotnet build` (with `--configuration Debug` in debug mode) then `dotnet run --no-build` from the EntryPoint directory. The working directory matters — FLT needs to find `WorkloadParameters/` relative to the EntryPoint.

### 5. Daemon Loop
Once running, edog enters a daemon loop that:
- **Monitors** the FLT process for crashes and auto-restarts
- **Refreshes** both tokens before they expire (~1 hour cycle)
- **Re-patches** source files with new tokens on refresh
- **Watches** for git changes (optional) and warns about conflicts with patches
- **Detects** stale patches from previous dirty exits (BSOD, `kill -9`)

---

## The Full Picture

```
┌──────────┐     ┌──────────────────┐     ┌─────────────────┐
│   User   │────▶│ Frontend Service │────▶│ Backend Service  │
│ (browser │     │   (edog PPE)     │     │  (Proxy nodes)   │
│  / REST) │     └──────────────────┘     └────────┬─────────┘
└──────────┘                                       │
                                                   │ Azure Relay
                                                   │ (bidirectional)
                                                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    Your Dev Machine                         │
│                                                             │
│  ┌─────────┐  auth + config + patch   ┌──────────────────┐  │
│  │  edog   │─────────────────────────▶│  FLT Service     │  │
│  │ (Python)│  launch + monitor        │  (dotnet, WCL)   │  │
│  │         │◀─────────────────────────│                  │  │
│  └─────────┘  crash/health signals    └──────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

edog is the **ground crew**. FLT + WCL SDK is the **pilot** that actually flies the relay connection.

---

## Common Failure Points

| Symptom | Likely Cause | edog Helps? |
|---------|-------------|-------------|
| FLT registers but gets no traffic | Wrong `CapacityGuid` — registered to a capacity nobody is using | ✅ edog syncs capacity from config |
| Health checks fail after a while | Relay connection dropped — network or MWC backend restart | ✅ edog detects crash, auto-restarts |
| "Capacity already in use" error | Another DevMode instance is registered to the same capacity | ✅ edog's instance lock prevents local duplicates |
| Registration fails entirely | Bad auth token, expired cert, wrong endpoint | ✅ edog cert diagnostics show exactly what's wrong |
| FLT starts but immediately exits | `workload-dev-mode.json` missing or malformed | ✅ edog auto-creates and validates this file |
| Browser popup appears on FLT start | `UserAuthorizationToken` missing or expired in config | ✅ edog injects this token silently |
| Patches conflict with git changes | Developer pulled new code while edog patches were applied | ✅ edog detects stale patches on startup |

---

## FLT Repo Structure (What edog Touches)

```
<flt-repo>/
├── Service/
│   ├── Microsoft.LiveTable.Service/              ← FLT service code
│   │   ├── Controllers/
│   │   │   ├── LiveTableController.cs            ← patched by edog
│   │   │   └── LiveTableSchedulerRunController.cs ← patched by edog
│   │   ├── SparkHttp/GTSBasedSparkClient.cs      ← patched by edog
│   │   ├── Telemetry/CustomLiveTableTelemetryReporter.cs
│   │   ├── WorkloadApp.cs                        ← patched by edog
│   │   └── DevMode/EdogLogServer.cs              ← created by edog
│   └── Microsoft.LiveTable.Service.EntryPoint/   ← dotnet run target
│       ├── Program.cs                            ← patched by edog
│       ├── Properties/launchSettings.json        ← configured by edog
│       └── WorkloadParameters/
│           ├── ParametersManifest.json
│           ├── Rollouts/Test.json
│           └── workload-dev-mode.json            ← created by edog
```

---

## All DevMode Parameters

Beyond the 5 fields edog auto-generates, the WCL SDK supports additional parameters. These can be set as command-line args (`-DevMode:ParamName="value"`) or in `workload-dev-mode.json`:

| Parameter | Required | Default | What It Does |
|-----------|----------|---------|-------------|
| `WorkloadStartUpMode` | ✅ | — | Must be `"DevMode"` |
| `CapacityGuid` | ✅ | — | Capacity whose traffic routes to your local workload |
| `TenantGuid` | ✅ | — | Tenant the test user belongs to |
| `MwcFrontendBaseEndpoint` | ✅ | — | MWC endpoint (e.g., `https://edog.pbidedicated.windows-int.net:443/`) |
| `LocalConfigFilePath` | ❌ | `C:\workload-dev-mode.json` | Path to the config file (command-line only — ignored if in the JSON itself) |
| `WorkloadToOrchestratorHealthCheckEnabled` | ❌ | `true` | If disabled, workload won't detect when Orchestrator kills the relay |
| `ChangeRoleDelaySeconds` | ❌ | `2` | Delay before workload transitions to Primary role. Increase if crashing during role change |
| `InitialHealthCheckDelaySeconds` | ❌ | `15` | How long Orchestrator waits before sending health checks. Increase if workload starts slowly |
| `UseManifestPublicProperty` | ❌ | `false` | Whether to honor manifest `public` scope on endpoints (needed for ASWL) |
| `WorkspaceAllowedRoutes` | ❌ | `[]` | Endpoints accessible via workspace-based routing instead of capacity-based |

**edog auto-manages:** `WorkloadStartUpMode`, `CapacityGuid`, `TenantGuid`, `MwcFrontendBaseEndpoint`, `EnvironmentType`, `UserAuthorizationToken`, and `LocalConfigFilePath` (via launchSettings.json).

---

## Debugging Tips (From the Trenches)

### "Is my request hitting my local workload?"
Check the HTTP response headers. If you see:
- **Routing header:** `Host proxy`
- **Via header:** contains the Azure Relay URL

...then your request was routed to your local DevMode instance. If these headers are missing, you're hitting the deployed workload, not yours.

### "Why isn't my breakpoint getting hit?"
Same answer — check the response headers. No `Host proxy` routing header = your request never reached your local machine.

### "Which DevMode instances are registered for my capacity?"
Run this Kusto query against `pbipkustppe.kusto.windows.net/pbipppe`:

```kusto
let capacityObjectId = "<your-capacity-guid>";
let registerRaids =
    ASTrace
    | where TIMESTAMP > ago(1d)
    | where MarkerName has "OR-Workload-Register"
    | where MessageText == "Workload registration request received"
    | extend WorkloadId = tostring(CustomData["WorkloadId"])
    | extend CapacityObjectId = tostring(CustomData["VirtualServiceObjectId"])
    | where CapacityObjectId has capacityObjectId
    | summarize by TIMESTAMP, WorkloadId, CapacityObjectId, RootActivityId;
ASTrace
| where TIMESTAMP > ago(1d)
| where MarkerName has "OR-DevX-WorkloadInstance-HealthMonitoring"
| join kind=inner(registerRaids) on RootActivityId
| summarize min(TIMESTAMP), max(TIMESTAMP) by RootActivityId, WorkloadId
| sort by min_TIMESTAMP asc
```

### Telemetry
When DevMode starts, the WCL SDK tries to launch the Geneva Monitoring Agent so your logs appear in the standard Kusto PPE tables. Look for:
- `"Geneva 'MonAgentLauncher' has been launched with PID ..."` → telemetry is flowing
- `"Could not find MonAgentLauncher binary"` → not installed; set `MWC_DEBUG_SERVICEPLATFORM_TRACER_LOCAL_DIR` env var to log to local filesystem instead

### CertificateKeyNotSupportedException
If CAE (Conditional Access Evaluation) is enabled for your workload, the S2SAuth cert must be installed locally. Download it from the [KeyVault](https://ms.portal.azure.com/#@microsoft.onmicrosoft.com/asset/Microsoft_Azure_KeyVault/Certificate/https://pbidedicatedoneboxrootkv.vault.azure.net/certificates/s2s-onebox-ame) as PFX and install in Machine Store.

---

## Supported Rollouts

- ✅ **EDog** (`https://edog.pbidedicated.windows-int.net:443/`)
- ✅ **CSTs** (e.g., `https://cst099.pbidedicated.windows-int.net:443/`)
- ✅ **INT3** and other PPE rollouts
- ❌ **Daily** — cannot be used
- ❌ **Production** — cannot be used

---

## Unsupported Features in DevMode (as of now)

These don't work in DevMode yet (per MWC team):
- Untrusted Workloads
- Capacityless Requests
- Premium Files
- Access Protection
- WASO
- Non-HTTP endpoints (WebSockets, raw TCP)

---

## Reference

- **MWC Wiki — First-Party DevX**: [dev.azure.com/powerbi/MWC/_wiki/wikis/MWC.wiki/94941](https://dev.azure.com/powerbi/MWC/_wiki/wikis/MWC.wiki/94941/First-Party-DevX)
- **Trident Wiki — Oneboxless Dev Experience**: [powerbi.visualstudio.com/Trident/_wiki/wikis/Trident.wiki/162028](https://powerbi.visualstudio.com/Trident/_wiki/wikis/Trident.wiki/162028/Workload-Oneboxless-DevExp)
- **Azure Relay docs**: [learn.microsoft.com/en-us/azure/azure-relay](https://learn.microsoft.com/en-us/azure/azure-relay/relay-what-is-it)
- **MWC DevMode support channel**: [Teams — MWC Oneboxless Development Onboarding](https://teams.microsoft.com/l/channel/19%3A1183393aca15419c87e56197d8b9d7bc%40thread.tacv2/MWC%20Oneboxless%20Development%20Onboarding)
- **Test tenant credentials**: [Fabric Shared Test Tenants](https://eng.ms/docs/cloud-ai-platform/azure-data/azure-data-intelligence-platform/microsoft-fabric-platform/fabric-platform-shared-services/fabric-platform-release-deployment/tsg/deployment/sharedtesttenants)
