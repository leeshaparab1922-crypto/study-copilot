from pydantic import BaseModel


class QuizQuestion(BaseModel):
    subject: str
    topic_name: str
    question_text: str
    options: list[str]
    correct_option_index: int


class QuizSet(BaseModel):
    subject: str
    topic_name: str
    questions: list[QuizQuestion]
