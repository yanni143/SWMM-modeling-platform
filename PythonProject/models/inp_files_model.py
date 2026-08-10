from sqlalchemy import Table, Column, String, Integer, BigInteger, Text, TIMESTAMP, MetaData
from sqlalchemy.dialects.postgresql import UUID

metadata = MetaData()

inp_files = Table(
    "inp_files",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("project_id", Text, nullable=False),
    Column("out_id", Text),
    Column("object_key", Text, nullable=False, unique=True),
    Column("filename", Text, nullable=False),
    Column("size_bigint", BigInteger),
    Column("content_type", Text),
    Column("checksum", Text),
    Column("version", Integer, default=1),
    Column("status", Text, default='pending'),
    Column("storage_bucket", Text),
    Column("created_by", Text),
    Column("created_at", TIMESTAMP),
    Column("updated_at", TIMESTAMP),
)

