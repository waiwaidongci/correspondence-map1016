from enum import StrEnum
class Role(StrEnum):
 ADMIN='admin'
 ANALYST='analyst'
 VIEWER='viewer'
class RunStatus(StrEnum):
 QUEUED='queued'
 RUNNING='running'
 SUCCEEDED='succeeded'
 FAILED='failed'
class NoteStatus(StrEnum):
 DRAFT='draft'
 APPROVED='approved'
 REJECTED='rejected'
class Axis(StrEnum):
 ROW='row'
 COLUMN='column'
class McStatus(StrEnum):
 QUEUED='queued'
 RUNNING='running'
 PAUSED='paused'
 SUCCEEDED='succeeded'
 INDETERMINATE='indeterminate'
 FAILED='failed'
 STALE='stale'
