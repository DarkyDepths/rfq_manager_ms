"""
SQLAlchemy model for atomic RFQ code counters.

One row per RFQ code prefix (e.g. IF, IB) stores the last allocated
numeric value. Allocation increments this value in the database.
"""

from sqlalchemy import Column, String, Integer

from src.database import Base


class RFQCodeCounter(Base):
    __tablename__ = "rfq_code_counter"

    prefix = Column(String(10), primary_key=True)
    last_value = Column(Integer, nullable=False)
