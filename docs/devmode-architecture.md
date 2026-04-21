# How DevMode Actually Works

> *You don't need to read this to use edog. But when the relay drops at 2am and you're staring at logs wondering why your workload went dark — you'll be glad you did.*

## The One-Sentence Version

Your local FLT service registers itself with the MWC cloud via an **Azure Relay** connection — there's no direct HTTP, no port forwarding, no tunneling. The relay IS the tunnel.

---

## Non-DevMode: How Normal Deployments Work

In a regular deployment, the workload lifecycle is fully cloud-managed:

1. Your workload executable gets pushed to an MWC-owned storage account during deployment
2. The **Orchestrator** process on a Backend node downloads and starts it
3. When requests hit **Frontend Service** for your workload, Frontend proxies them to the workload's HTTP endpoints

```
User → Frontend Service → Backend Service → Workload (running on Backend node)
```

Simple. You deploy, Orchestrator runs it, traffic flows through MWC's internal network. No magic.

---

## DevMode: The Relay Architecture

DevMode flips the script. Orchestrator doesn't start your workload — **you do**, on your own machine. But the cloud still needs to reach you. That's where Azure Relay comes in.

### Registration Flow

1. **Your workload** (via WCL SDK) calls **Frontend Service** to register itself for a specific capacity
2. **Frontend Service** proxies the registration to **Backend Service**
3. **Backend Service** creates a new relay inside an **Azure Relay Namespace** and starts listening
4. Relay details flow back: Backend → Frontend → Your workload
5. **Your workload** starts listening on the relay and initializes the workload context

### What Happens After Registration

Two things run continuously:

- **Health checks** — bidirectional. Backend pings your workload through the relay, your workload pings Backend. If either side goes silent, things break.
- **User traffic** — `User → Frontend → Backend → Azure Relay → Your local workload`. If your workload needs platform info, it calls Backend back through the same relay.

### The Key Insight

There is **no localhost port being exposed to the internet**. Your workload doesn't bind to `localhost:5000` and wait for inbound connections. Instead, it opens an **outbound** connection to Azure Relay and listens there. The cloud reaches you through the relay, not by connecting to your machine directly.

This is why Dev Tunnels / ngrok / port forwarding are all irrelevant here — the platform already solved the "cloud can't reach localhost" problem with Azure Relay.

---

## What `workload-dev-mode.json` Does

This file is the entire configuration that makes DevMode work:

```json
{
  "TenantGuid": "<from your JWT's tid claim>",
  "CapacityGuid": "<the capacity ID you're taking traffic for>",
  "MwcFrontendBaseEndpoint": "<which MWC environment to register with>",
  "WorkloadStartUpMode": "DevMode",
  "EnvironmentType": "PPE"
}
```

When the WCL SDK sees `"WorkloadStartUpMode": "DevMode"`, it skips waiting for Orchestrator and instead uses the endpoint + capacity info to self-register with the relay. That's the entire difference between "normal deployment" and "DevMode."

---

## The Traffic Flow (Visual)

```
┌──────────┐     ┌──────────────────┐     ┌─────────────────┐
│   User   │────▶│ Frontend Service │────▶│ Backend Service  │
│ (browser │     │   (edog / CST)   │     │  (Proxy nodes)   │
│  / REST) │     └──────────────────┘     └────────┬─────────┘
└──────────┘                                       │
                                                   │ Azure Relay
                                                   │ (bidirectional)
                                                   ▼
                                          ┌─────────────────┐
                                          │  Your Workload   │
                                          │  (local machine) │
                                          └─────────────────┘
```

Key detail: Backend uses special **"Proxy" backend nodes** for DevMode traffic. These are the nodes that bridge the relay connection.

---

## What edog Does In This Picture

edog doesn't touch the relay — the WCL SDK handles all of that. What edog does:

1. **Authenticates** you silently (CBA certs, no browser popups)
2. **Generates** `workload-dev-mode.json` with the right values
3. **Patches** the FLT service DLL with your auth token
4. **Starts** the FLT service process (which then self-registers via WCL SDK)
5. **Monitors** health and auto-recovers on crashes
6. **Re-patches** when tokens expire (every ~1 hour)

edog is the **setup and lifecycle manager**. The relay communication is entirely between the WCL SDK in your workload and the MWC Backend Service.

---

## Common Failure Points

| Symptom | Likely Cause |
|---------|-------------|
| Workload registers but gets no traffic | Wrong `CapacityGuid` — you're registered to a capacity nobody is using |
| Health checks fail | Relay connection dropped — could be network, could be MWC backend restart |
| "Capacity already in use" error | Another DevMode instance (yours or someone else's) is registered to the same capacity |
| Registration fails entirely | Bad auth token, expired cert, or wrong `MwcFrontendBaseEndpoint` |
| Workload starts but immediately exits | `workload-dev-mode.json` missing or malformed — WCL SDK can't find registration config |

---

## Reference

- **MWC Wiki — First-Party DevX**: [dev.azure.com/powerbi/MWC/_wiki/wikis/MWC.wiki/94941](https://dev.azure.com/powerbi/MWC/_wiki/wikis/MWC.wiki/94941/First-Party-DevX)
- **Detailed setup guide**: [Trident Wiki — Oneboxless Dev Experience](https://powerbi.visualstudio.com/Trident/_wiki/wikis/Trident.wiki/162028/-PrPre-New-Oneboxless-Dev-Experience)
- **Azure Relay docs**: [learn.microsoft.com/en-us/azure/azure-relay](https://learn.microsoft.com/en-us/azure/azure-relay/relay-what-is-it)
