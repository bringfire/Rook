# Command Gotchas

Document command-specific gotchas that are relevant to this skill.

## Example Format

### Command: `-Loft`

**Issue:** Loft creates open surfaces by default
**Solution:** Use `_-Cap` command after lofting to create solid

### Command: `-BooleanDifference`

**Issue:** Boolean fails when cutter is fully contained inside target
**Solution:** Cutter must extend through at least one target surface

## Querying Knowledge

For the latest gotchas, query the knowledge system:

```python
knowledge_query(tool="rhino_execute_intent", intent="your operation", depth="errors")
```

This returns learned gotchas from `knowledge/commands/command_knowledge.json`.
