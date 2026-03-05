Research and document the EarthBound Zero (Mother 1) NES RAM map. Update @docs/MEMORY_MAP.md with confirmed addresses.

Research approach:
1. Search the web for "EarthBound Zero RAM map", "Mother 1 NES memory addresses", "EarthBound Zero TAS resources"
2. Check datacrystal.romhacking.net for Mother / Earth Bound entries
3. Check TASVideos.org for Mother 1 game resources and Lua scripts
4. Search GitHub for existing FCEUX Lua scripts for EarthBound Zero / Mother 1
5. Cross-reference multiple sources to confirm addresses

For each address found:
- Record the hex address, byte size, data type
- Note which ROM version it was tested on
- Add the source URL

Priority addresses (Phase 1 minimum):
- Player X/Y position
- Current map ID
- Ninten HP / Max HP
- Battle flag (in-battle vs overworld)
- Menu state
- Dialog active flag

After researching, update docs/MEMORY_MAP.md with all confirmed addresses. Change "TBD" entries to actual values. Add source citations.

If you can't find a specific address, document what you DID find and suggest an empirical approach (e.g., "use FCEUX RAM Search: take damage, search for decreased 2-byte value").
