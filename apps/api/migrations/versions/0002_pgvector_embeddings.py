"""Use pgvector for chunk embeddings on PostgreSQL.

On SQLite the embedding column stays JSON: pgvector is a PostgreSQL extension
and the local fallback must remain dependency-free. The application reads either
representation through ``VectorType``.
"""
from __future__ import annotations

from alembic import op

revision = "0002_pgvector_embeddings"
down_revision = "fe36824895c5"
branch_labels = None
depends_on = None

DIMENSION = 256


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(f"ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector({DIMENSION}) USING embedding::text::vector")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding "
        f"ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE json USING embedding::text::json")
