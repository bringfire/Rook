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
knowledge_query(tool="<explicit admitted tool>", intent="your operation", depth="errors")
```

Use the result to select and preflight an explicit typed route or, only when no
typed route fits, a fully scripted non-interactive command. Verify the host result
after execution.
