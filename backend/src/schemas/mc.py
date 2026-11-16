from pydantic import BaseModel,Field
class McInput(BaseModel):
 study_id:int=Field(gt=0)
 name:str=Field(min_length=1,max_length=100)
 seed:int=Field(ge=0,le=2_147_483_647,strict=True)
 epsilon:float=Field(gt=0.00009,lt=0.10001)
 min_draws:int=Field(ge=100,le=10_000_000,strict=True)
 max_draws:int=Field(ge=100,le=10_000_000,strict=True)
 batch_size:int=Field(ge=10,le=100_000,strict=True)
class McPatch(BaseModel):
 status:str=Field(pattern='^(running|paused)$')
