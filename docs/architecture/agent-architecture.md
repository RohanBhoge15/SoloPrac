# SoloPrac AI — Agent Architecture Design

## 1. Agentic Framework

The agent system is built on **LangGraph** — a graph-based framework for orchestrating LLM agents. Unlike linear chains, LangGraph allows cyclic execution (plan-execute-critic loops), conditional branching, and dynamic tool selection.

---

## 2. Agent Components

### 2.1 Intent Router (Llama-3.1-8B via NIM)
The entry point for all user queries. A lightweight LLM that classifies intent and routes to the appropriate tool.

**Classification Categories:**
```
patient_qa       → RAG retrieval + synthesis
image_analysis   → Vision model (Groq 90B-V or MedGemma-4B)
document_parse   → OCR pipeline (Docling/Surya/Nanonets-OCR2) + quality alerts
scheduling       → Calendar subgraph (9 tools)
prescription     → JSON Schema + PDF generation (state-specific)
invoice          → Billing → PDF
certificate      → Certificate template → PDF
image_compare    → ORB matching + overlay
weekly_report    → Significance scorer + PDF
general_chat     → Direct Maverick response
```

### 2.2 RAG Retrieval Node (Feature A)
Executes temporal-aware multimodal retrieval from Qdrant. Implements the formal scoring function with temporal decay and clinical significance weighting.

### 2.3 Response Synthesizer (Llama-4 Maverick via NIM)
Generates the final response grounded in retrieved context. Uses structured output and post-processing citation validation.

### 2.4 Vision Analysis Node
Routes to MedGemma-4B-IT (local) for radiology/dermatology or Groq fallback for general medical images.

### 2.5 Document Processor Node
Multi-stage pipeline: file type detection → quality check (blur, contrast, brightness, resolution) → parser selection (Docling/Surya/Nanonets-OCR2) → text extraction → schema alignment (Feature D) → structured patient data.

### 2.6 Image Registration Node
OpenCV ORB feature matching pipeline for wound/skin comparison.

### 2.7 Calendar Subgraph (9 Tools)
Specialized subgraph with locked tool set for booking, rescheduling, cancellation, and smart rearrangement.

### 2.8 Voice Scheduling Flow (Hindi + English)
```
[Mic] → faster-whisper/IndicWhisper → [Transcript]
  → Maverick intent: scheduling only (5 locked commands)
  → Tool execution (parallel where independent)
  → Approval card to doctor UI
  → Confirm → arq emails → audit log → Indic-Parler-TTS confirmation
```

### 2.9 Voice-to-Text (PrescriptionBox + ChatUI)
```
[Mic button] → MediaRecorder (browser) → audio blob
  → POST /api/v1/voice/transcribe
  → faster-whisper/IndicWhisper → text
  → Fill text field (diagnosis, instructions, or chat input)
```
Returns 503 with guidance if ASR model not installed.

---

## 3. Streaming Architecture

Agent-trace events stream to UI via SSE:
```
event: trace
data: {"node": "router", "status": "completed", "output": {"intent": "patient_qa"}}

event: token
data: {"token": "Mrs.", "citation": null}

event: done
data: {"response_id": "uuid"}
```

---

## 4. Error Handling Strategy

| Failure Mode | Handling | Fallback |
|-------------|----------|----------|
| NIM API down | Retry 2x with exponential backoff | "Service degraded, please retry" |
| Groq rate limit | Cache current response; queue request | Use cached or simplified response |
| Qdrant timeout | Retry with simplified query | Return last N versions from SQL |
| MedGemma OOM | Unload, restart, retry | Use Groq 90B-V as fallback |
| OCR failure (all engines) | Return error with suggestion | "Please upload a clearer image" |
| Voice ASR low confidence | Request rephrasing | "Could you please repeat that?" |
| ASR model not installed | Return 503 with guidance | "Install faster-whisper for voice input" |
| OCR quality poor | Show amber warnings | Doctor decides whether to proceed |

---

## 5. Langfuse Observability

Every agent step is traced:
- **Root span:** Full user request
- **Nested spans:** Each node execution (router, retrieval, synthesis, tool)
- **Evaluation:** LLM-as-judge for answer faithfulness (Feature A metric)
- **Metrics:** Step count, latency per node, token usage, success rate

---

## 6. Paper Contributions Mapped to Agent

| Feature | Agent Component | Evaluation |
|---------|----------------|------------|
| **A** — Temporal RAG | Retrieval node with temporal scoring | Recall@5, future-leak rate, latency |
| **B** — Self-Planning | Planner-Executor-Critic loop | Steps-to-resolution vs fixed pipeline |
| **C** — Cross-Modal | Image retrieval via projected embeddings | Recall@k on CheXpert pairs |
| **D** — Schema Alignment | Document processor node | Field-level F1 across 5 doc types (manual eval) |
| **E** — Clustering | Offline trajectory analysis | Precision on injected deteriorations |
| **F** — Reports | Significance scorer + PDF pipeline | Likert rating vs unfiltered baseline (manual eval) |
