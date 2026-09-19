# Workflow files

See [setup and human review](../docs/workflows.md) for import, testing, approval, and scheduling instructions.

The checked-in Execute Sub-workflow IDs are placeholders: select workflow 03 in 02 and workflow 02 in 01 after import. Workflow 01 uses batch size 1 and waits for each child. Both qualification branches in 02 return an item so the parent loop continues. A stage failure stops the run; inspect PostgreSQL's recorded error and retry the persisted lead through a child manual input.

HTTP Request nodes allow 60 minutes per bounded worker call and executions allow twelve hours for up to five sequential leads. Worker endpoints load research from PostgreSQL; n8n transfers lead IDs between stages. Run `python scripts/validate_config.py` for static JSON/link checks. Installed n8n node versions and import/execution must still be verified with the running stack.
