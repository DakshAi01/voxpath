---
pdf_options:
  format: A3
  margin: 20mm
  landscape: true
---

# VoxPath — Visual Overview

A set of diagrams that show how VoxPath fits together: the system architecture,
the shared tool layer, and the main request flows (voice, chat, image→video, news).

---

## 1. System Architecture

```mermaid
flowchart TB
    subgraph BROWSER["🌐 Browser — Next.js 16 / React 19"]
        direction LR
        V["/voice<br/>VoiceInterface"]
        C["/chat<br/>ChatInterface"]
        VID["/video<br/>VideoStudio"]
        N["/news<br/>NewsDashboard"]
        M["/market"]
        MCPUI["/mcp"]
    end

    subgraph API["⚙️ Backend — FastAPI (main.py · :8000)"]
        direction TB
        WS["/ws/voice"]
        CHAT["/chat"]
        NEWSEP["/news/*"]
        IMG["/image/generate"]
        VEP["/video/*"]
        MOUNT["/mcp (mounted MCP HTTP app)"]
        SCHED["news_scheduler<br/>(background crawler)"]
    end

    subgraph AGENTS["🤖 Agents"]
        TXT["agent.py<br/>LangGraph ReAct"]
        VOICE["voice_live.py<br/>Gemini Live bridge"]
    end

    MCP{{"🧩 MCP SERVER<br/>mcp_server.py<br/>single tool registry"}}

    subgraph CAP["🛠️ Capability modules"]
        direction LR
        SVC["services.py<br/>LLM + market + news"]
        CRAWL["news_crawler.py"]
        RAIL["railway.py"]
        STOCK["stock_resolver.py"]
        IG["image_gen.py"]
        VD["video.py"]
    end

    subgraph EXT["☁️ External services"]
        direction LR
        VERTEX["Vertex AI<br/>Gemini · Live · Veo · Nano Banana"]
        YF["Yahoo Finance<br/>(yfinance)"]
        IRCTC["IRCTC API<br/>(RapidAPI)"]
        SITES["News sites<br/>(RSS / HTML)"]
        NSE["NSE equity list"]
    end

    V <-->|"PCM16 audio<br/>(WebSocket)"| WS
    C -->|"POST"| CHAT
    VID -->|"multipart + poll"| IMG
    VID --> VEP
    N -->|"GET / POST"| NEWSEP
    M --> CHAT
    MCPUI --> MOUNT

    WS --> VOICE
    CHAT --> TXT
    TXT --> MCP
    VOICE --> MCP
    NEWSEP --> MCP
    MOUNT --- MCP
    IMG --> IG
    VEP --> VD
    SCHED --> CRAWL

    MCP --> SVC
    MCP --> CRAWL
    MCP --> RAIL
    SVC --> STOCK

    SVC --> VERTEX
    SVC --> YF
    VOICE --> VERTEX
    IG --> VERTEX
    VD --> VERTEX
    RAIL --> IRCTC
    CRAWL --> SITES
    STOCK --> NSE

    classDef browser fill:#1e293b,stroke:#7c3aed,color:#e2e8f0;
    classDef api fill:#0f172a,stroke:#06b6d4,color:#e2e8f0;
    classDef agent fill:#312e81,stroke:#a78bfa,color:#ede9fe;
    classDef mcp fill:#7c3aed,stroke:#c4b5fd,color:#ffffff;
    classDef cap fill:#064e3b,stroke:#34d399,color:#d1fae5;
    classDef ext fill:#7c2d12,stroke:#fb923c,color:#ffedd5;

    class V,C,VID,N,M,MCPUI browser;
    class WS,CHAT,NEWSEP,IMG,VEP,MOUNT,SCHED api;
    class TXT,VOICE agent;
    class MCP mcp;
    class SVC,CRAWL,RAIL,STOCK,IG,VD cap;
    class VERTEX,YF,IRCTC,SITES,NSE ext;
```

---

## 2. The MCP Tool Layer — "Two agents, one registry"

```mermaid
flowchart LR
    subgraph SURFACES["User surfaces"]
        TXTUSER["⌨️ Text chat"]
        VOICEUSER["🎙️ Live voice"]
    end

    subgraph A["Agents"]
        AGENT["agent.py<br/>LangChain StructuredTools<br/>(subset of tools)"]
        VL["voice_live.py<br/>Gemini Live<br/>FunctionDeclarations"]
    end

    REG{{"🧩 FastMCP registry<br/>call_tool(name, args)"}}

    subgraph TOOLS["Registered MCP tools"]
        direction TB
        T1["get_latest_news"]
        T2["get_latest_headlines"]
        T3["crawl_news"]
        T4["get_stock_price"]
        T5["market_report"]
        T6["get_pnr_status"]
        T7["resolve_station_code"]
        T8["get_live_train_status"]
        T9["get_train_schedule"]
        T10["search_trains"]
        T11["check_seat_availability"]
        T12["get_fare"]
    end

    subgraph RES["MCP resources"]
        R1["voxpath://health"]
        R2["voxpath://capabilities"]
        R3["voxpath://news/sources"]
    end

    TXTUSER --> AGENT --> REG
    VOICEUSER --> VL --> REG
    REG --> TOOLS
    REG -.-> RES

    classDef u fill:#1e293b,stroke:#7c3aed,color:#e2e8f0;
    classDef ag fill:#312e81,stroke:#a78bfa,color:#ede9fe;
    classDef rg fill:#7c3aed,stroke:#c4b5fd,color:#ffffff;
    classDef tl fill:#064e3b,stroke:#34d399,color:#d1fae5;
    classDef rs fill:#0c4a6e,stroke:#38bdf8,color:#e0f2fe;
    class TXTUSER,VOICEUSER u;
    class AGENT,VL ag;
    class REG rg;
    class T1,T2,T3,T4,T5,T6,T7,T8,T9,T10,T11,T12 tl;
    class R1,R2,R3 rs;
```

---

## 3. Live Voice Flow (voice‑to‑voice)

```mermaid
sequenceDiagram
    autonumber
    participant U as 🎙️ User
    participant B as Browser<br/>(AudioWorklet)
    participant WS as /ws/voice
    participant G as Gemini Live<br/>(Vertex, global)
    participant MCP as MCP tool

    U->>B: speaks
    B->>WS: 16kHz PCM16 (binary frames)
    WS->>G: forward audio (Blob)
    Note over G: server-side VAD<br/>detects end of turn
    alt model needs live data
        G->>WS: tool_call
        WS->>MCP: call_tool(name, args)
        MCP-->>WS: result (dict)
        WS->>G: FunctionResponse
    end
    G->>WS: 24kHz PCM16 answer + transcripts
    WS->>B: audio frames + JSON control
    B->>U: plays answer (jitter-buffered)
    Note over B: mic muted while speaking<br/>(half-duplex); barge-in flushes playback
```

---

## 4. Text Chat Flow

```mermaid
sequenceDiagram
    autonumber
    participant U as ⌨️ User
    participant UI as ChatInterface
    participant API as POST /chat
    participant AG as LangGraph agent
    participant LLM as ChatVertexAI (Gemini)
    participant MCP as MCP tool

    U->>UI: types message
    UI->>API: { message }
    API->>AG: agent_chat(message)
    AG->>LLM: reason about intent
    LLM-->>AG: decide tool call
    AG->>MCP: call tool (news / market / railway)
    MCP-->>AG: live data
    AG->>LLM: compose answer from data
    LLM-->>AG: final text
    AG-->>API: reply text
    API-->>UI: { text }
    UI-->>U: renders answer
    Note over API: quota error → friendly fallback (not 500)
```

---

## 5. Image → Video Flow

```mermaid
sequenceDiagram
    autonumber
    participant U as 🎨 User
    participant VS as VideoStudio
    participant IMG as POST /image/generate
    participant NB as Nano Banana<br/>(Gemini 2.5 Flash Image)
    participant VG as POST /video/generate
    participant JOB as async job
    participant VEO as Veo (Vertex)

    opt generate source image
        U->>VS: image prompt
        VS->>IMG: { prompt }
        IMG->>NB: text → image
        NB-->>IMG: PNG bytes
        IMG-->>VS: image (becomes source)
    end
    U->>VS: motion prompt + aspect ratio
    VS->>VG: multipart (image, prompt, ratio)
    VG->>JOB: start background task
    VG-->>VS: { job_id, running }
    JOB->>VEO: start long-running op
    loop poll every 10s (server) / 5s (client)
        VEO-->>JOB: status
        VS->>VG: GET /video/status/{id}
    end
    JOB->>JOB: write generated_videos/{id}.mp4
    VS->>VG: GET /video/result/{id}
    VG-->>VS: MP4 → play + download
```

---

## 6. News Subsystem

```mermaid
flowchart TB
    subgraph SCHED["⏱️ Background scheduler (every 5 min)"]
        LOOP["news_scheduler._loop"]
    end

    subgraph CRAWLER["news_crawler.crawl_news"]
        FETCH["Fetch sources<br/>ThreadPool · rate-limited"]
        PARSE["Parse RSS (xml)<br/>+ HTML (BeautifulSoup)"]
        VALID["Validate + normalize<br/>(mojibake, NFKC, noise filter)"]
        DEDUP["Dedup<br/>SHA-256 hash + Jaccard similarity"]
    end

    STORE[("data/news/<br/>headlines_YYYY-MM-DD.jsonl<br/>+ seen_hashes.json")]

    subgraph READERS["Readers"]
        TOOL["get_latest_news / get_latest_headlines<br/>(voice + chat tools)"]
        DASH["NewsDashboard<br/>/news/headlines"]
    end

    SITES["📰 ~17 sources<br/>(ToI, Hindu, NDTV, Jagran,<br/>Bihar & UP regional…)"]

    LOOP --> CRAWLER
    DASH -- "Run Fresh Crawl<br/>POST /news/crawl" --> CRAWLER
    SITES --> FETCH --> PARSE --> VALID --> DEDUP --> STORE
    STORE --> TOOL
    STORE --> DASH

    classDef s fill:#1e293b,stroke:#7c3aed,color:#e2e8f0;
    classDef c fill:#064e3b,stroke:#34d399,color:#d1fae5;
    classDef st fill:#7c2d12,stroke:#fb923c,color:#ffedd5;
    classDef r fill:#0c4a6e,stroke:#38bdf8,color:#e0f2fe;
    class LOOP s;
    class FETCH,PARSE,VALID,DEDUP c;
    class STORE,SITES st;
    class TOOL,DASH r;
```

---

## 7. Technology Stack at a Glance

```mermaid
mindmap
  root((VoxPath))
    Frontend
      Next.js 16 / React 19
      TypeScript 5
      Tailwind CSS v4
      Web Audio API
        AudioWorklet
        WebSocket
      lucide-react
    Backend
      FastAPI + Uvicorn
      FastMCP
      LangChain + LangGraph
      google-genai SDK
      requests + BeautifulSoup
      yfinance + pandas
    AI / Cloud
      Vertex AI
        Gemini 2.5 Flash
        Gemini Live
        Veo (video)
        Nano Banana (image)
    Data sources
      IRCTC via RapidAPI
      Yahoo Finance
      NSE equity list
      News RSS / HTML
    Storage
      JSONL on disk
      Rotating logs
      Trace ids
```

---

*Diagrams rendered with Mermaid. Edit this file and regenerate the PDF/PNG to keep
the visuals in sync with the code.*
```