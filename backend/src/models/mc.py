from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import String,JSON,ForeignKey,DateTime,Integer,Boolean
from datetime import datetime,timezone
from src.config.database import Base
class MonteCarloRun(Base):
 __tablename__='monte_carlo_runs'
 id:Mapped[int]=mapped_column(primary_key=True)
 study_id:Mapped[int]=mapped_column(ForeignKey('contingency_studies.id'))
 name:Mapped[str]=mapped_column(String(100))
 seed:Mapped[int]=mapped_column(Integer)
 epsilon:Mapped[float]=mapped_column()
 min_draws:Mapped[int]=mapped_column(Integer)
 max_draws:Mapped[int]=mapped_column(Integer)
 batch_size:Mapped[int]=mapped_column(Integer)
 status:Mapped[str]=mapped_column(String(20),default='queued')
 result:Mapped[dict]=mapped_column(JSON,default=dict)
 error:Mapped[str|None]=mapped_column(String(1000),nullable=True)
 source_fingerprint:Mapped[str]=mapped_column(String(64))
 is_stale:Mapped[bool]=mapped_column(Boolean,default=False)
 stale_reason:Mapped[str|None]=mapped_column(String(200),nullable=True)
 ledger:Mapped[dict]=mapped_column(JSON,default=dict)
 pending_batches:Mapped[dict]=mapped_column(JSON,default=dict)
 in_flight:Mapped[dict]=mapped_column(JSON,default=dict)
 stop_index:Mapped[int|None]=mapped_column(Integer,nullable=True)
 creator_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
 updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
