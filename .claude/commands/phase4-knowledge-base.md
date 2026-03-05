Implement Phase 4: Knowledge Base & Context Management. Read @docs/SPEC.md and @docs/ARCHITECTURE.md (ADR-004, ADR-005).

Your tasks:
1. Create `src/knowledge_base/kb.py` — KnowledgeBase class:
   - Internal dict with sections: map_data, npc_notes, battle_strategies, inventory, objectives, death_log
   - Methods: read(section, key), write(section, key, value), delete(section, key), list_sections()
   - Auto-save to `data/knowledge_base.json` on every write
   - Load from file on init if exists

2. Create `src/knowledge_base/summarizer.py` — progressive summarization:
   - Monitor conversation history length (count tool calls)
   - When threshold exceeded (~50 calls), prompt Claude to write a progress summary
   - Return the summary text to be used as new conversation seed
   - Preserve knowledge base (it's external to conversation history)

3. Create `src/knowledge_base/session.py` — session save/restore:
   - Save: emulator save state ID + knowledge_base.json path + last summary text + timestamp
   - Restore: reload save state, load knowledge base, inject summary as context
   - Save sessions to `data/sessions/` directory

4. Update `src/mcp_server/server.py` — integrate update_knowledge_base tool with KnowledgeBase class

5. Create `tests/test_knowledge_base.py` — unit tests for CRUD operations and persistence

6. Create `tests/test_summarizer.py` — test summarization trigger logic

The knowledge base is Claude's long-term memory. It should be human-readable (check the JSON files to see what Claude is learning). Keep values as natural language strings — Claude is the reader.
