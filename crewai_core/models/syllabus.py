from pydantic import BaseModel, Field


class SyllabusSubTopic(BaseModel):
    sub_topic_name: str


class SyllabusTopic(BaseModel):
    topic_name: str
    sub_topics: list[str] = Field(default_factory=list)


class SyllabusUnit(BaseModel):
    unit_name: str
    weightage_percent: float
    topics: list[SyllabusTopic]


class SyllabusStructure(BaseModel):
    grade: str
    subject: str
    units: list[SyllabusUnit]
