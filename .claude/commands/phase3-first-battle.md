Implement Phase 3: First Playthrough Milestone. Read @docs/SPEC.md for full specification.

Your tasks:
1. Create `docs/system_prompt.md` — the system prompt Claude will use when playing. Include:
   - Role description (you are playing EarthBound Zero)
   - Available tools and when to use each
   - Core loop: observe (get_game_state) → think → act (execute_action) → repeat
   - Basic EarthBound Zero mechanics (turn-based battles, BASH/PSI/GOODS/RUN, HP/PP system)
   - Battle strategy: BASH for basic attacks, heal when HP < 30%, RUN from dangerous enemies
   - Exploration strategy: talk to NPCs, check items, save often
   - Knowledge base usage: write notes about discoveries, read before making decisions

2. Create `scripts/test_title_screen.py` — automated test that Claude can navigate title screen and start new game

3. Create `scripts/test_first_battle.py` — automated test that Claude can detect battle, select BASH, and win

4. Create `src/bridge/auto_checkpoint.py` — logic for automatic save state creation:
   - Save when entering a new map_id
   - Save when HP is at max after healing
   - Save every N minutes of real time
   - Restore on game over detection

5. Create `scripts/run_session.py` — the main gameplay loop:
   - Load system prompt
   - Initialize MCP server and knowledge base
   - Run observe → Claude API call → execute action loop
   - Handle progressive summarization trigger
   - Log every decision with timestamp and screenshot

This phase is where we first connect Claude to the live game. Start with the system prompt, then the session runner, then the test scripts.
