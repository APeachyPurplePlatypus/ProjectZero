# Architecture Decisions

## ADR-001: FCEUX as Emulator

**Decision:** Use FCEUX as the NES emulator.

**Context:** Evaluated FCEUX, Mesen, BizHawk, and Nestopia. Need: Lua scripting, memory API, headless/CLI mode, cross-platform, active community.

**Rationale:**
- Full Lua 5.1 scripting with per-frame memory access and input injection
- Largest TAS community → most existing scripts and documentation
- CLI mode supported for headless operation
- Cross-platform (Linux, macOS, Windows)
- BizHawk was close second but is Windows-centric and requires EmuHawk GUI

**Tradeoff:** FCEUX accuracy is slightly lower than Mesen, but accuracy doesn't matter for AI gameplay — we need API richness.

**Fallback:** BizHawk if FCEUX Lua API proves insufficient.

---

## ADR-002: File-Based IPC

**Decision:** Use shared JSON files for communication between FCEUX Lua and Python bridge.

**Context:** Options considered: TCP sockets, named pipes, shared memory, file-based.

**Rationale:**
- Simplest to implement and debug (just read/write JSON files)
- Works cross-platform without OS-specific APIs
- FCEUX Lua has file I/O but no socket library built in
- Latency is acceptable (~1-5ms for file read at SSD speeds)
- Easy to inspect state by just reading the JSON file

**Tradeoff:** Slightly higher latency than shared memory or sockets. File locking needed to prevent races.

**Mitigation:** Use atomic write (write to temp file, rename) and monotonic frame counter for staleness detection.

---

## ADR-003: Memory-First, Vision-Fallback

**Decision:** Primary game state comes from memory reads. Vision (screenshots + Claude vision API) is a supplement, not the primary source.

**Context:** Could use vision-only (like a human watching the screen), memory-only, or hybrid.

**Rationale:**
- Memory reads are instant, precise, and cheap (no API tokens)
- Vision is expensive (screenshot → base64 → Claude vision = many tokens per observation)
- Memory gives us exact HP, position, battle state — no OCR errors
- Vision is needed for: map layout understanding, NPC identification, text that isn't in simple memory locations

**Usage pattern:**
- Routine observations: memory only (get_game_state with include_screenshot: false)
- New area exploration: include screenshot for spatial awareness
- Ambiguous states: include screenshot for Claude to visually assess

---

## ADR-004: Knowledge Base Architecture

**Decision:** Use a Python dict with JSON persistence, modeled after Claude Plays Pokémon.

**Context:** Options: database, vector store, flat files, in-memory dict.

**Rationale:**
- Dict is simple, inspectable, and matches the proven Pokémon architecture
- JSON persistence means human-readable save files
- Sections (map_data, battle_strategies, etc.) keep knowledge organized
- Claude writes natural language notes — no need for structured DB queries
- Can always upgrade to a database later if needed

**Sections:**
- `map_data` — Discovered map layouts, connections, landmarks
- `npc_notes` — What NPCs said, quest info
- `battle_strategies` — What works against which enemies
- `inventory` — Item management notes
- `objectives` — Current goals and progress
- `death_log` — How/where Claude died and what to try differently

---

## ADR-005: Progressive Summarization for Context

**Decision:** Use progressive summarization to manage context window limits.

**Context:** Extended gameplay will exceed Claude's context window. Need a strategy to maintain continuity.

**Rationale:**
- Proven pattern from Claude Plays Pokémon
- When conversation history exceeds ~50 tool calls, Claude writes a progress summary
- History is cleared; summary becomes first assistant message
- Knowledge base persists independently — it's never lost to summarization
- Cheaper than maintaining full history in every request

**Flow:**
1. Core loop runs: observe → think → act
2. After N tool calls, trigger summarization
3. Claude writes summary of recent progress
4. Clear conversation history
5. New conversation starts with: system prompt + knowledge base + summary
