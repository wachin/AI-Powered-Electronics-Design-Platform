# Historical Prototypes

These scripts are **not part of the platform**. They are the proof-of-concept
work used to validate the approach during Phase 1, before `src/` existed.

| Prototype | What it demonstrated | Where it lives now |
|---|---|---|
| `poc_ai_orchestration.py` | The AI orchestration loop end to end | `src/agents/orchestrator.py` |
| `poc_component_search.py` | Component lookup against the catalog | `src/components/database.py` |
| `poc_mcp_integration.py` | Talking to an MCP server over stdio | `src/agents/mcp_client.py`, `src/agents/mcp_servers.py` |
| `poc_phase1_validation.py` | Phase 1 acceptance checks | `tests/` (239 tests) |

They are kept because they document how the architecture was arrived at, and
`research/phase1_validation_instructions.md` refers to them. They are not
imported, tested or maintained.

Run one directly if you are curious:

```bash
python docs/prototypes/poc_phase1_validation.py
```
