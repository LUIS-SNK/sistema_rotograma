from alembic import context
connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("Execute a migração pelo comando atualizar-banco do aplicativo.")
context.configure(connection=connection, target_metadata=None)
with context.begin_transaction():
    context.run_migrations()
