import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Integer, Float, BigInteger, DateTime, ForeignKey, CheckConstraint,
    Boolean, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

def utcnow():
    return datetime.now(timezone.utc)

class Course(Base):
    __tablename__ = "courses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    code = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    sources = relationship("Source", back_populates="course", cascade="all, delete-orphan")


class Source(Base):
    __tablename__ = "sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    source_type = Column(String(20), nullable=False)  # 'pdf', 'pptx', 'video', 'image'
    file_path = Column(String(1024), nullable=False)
    mime_type = Column(String(100), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    status = Column(String(30), default="queued", nullable=False, index=True)  # queued, processing, completed, failed
    error_message = Column(Text, nullable=True)
    source_metadata = Column("metadata", JSONB, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    course = relationship("Course", back_populates="sources")
    processing_jobs = relationship("ProcessingJob", back_populates="source", cascade="all, delete-orphan", order_by="desc(ProcessingJob.created_at)")
    content_units = relationship("ContentUnit", back_populates="source", cascade="all, delete-orphan", order_by="ContentUnit.sequence_index")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    state = Column(String(30), default="queued", nullable=False)  # queued, processing, completed, failed
    stage = Column(String(50), default="upload_validated", nullable=False)
    progress_percent = Column(Integer, default=0, nullable=False)
    error_detail = Column(JSONB, nullable=True)
    attempt_number = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    source = relationship("Source", back_populates="processing_jobs")


class ContentUnit(Base):
    __tablename__ = "content_units"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(20), nullable=False)  # 'pdf', 'pptx', 'video', 'image'
    unit_type = Column(String(30), nullable=False)  # 'text', 'caption', 'slide', 'keyframe', 'diagram', 'image', 'heading'
    content = Column(Text, nullable=False)
    vision_caption = Column(Text, nullable=True)
    ocr_text = Column(Text, nullable=True)
    page_number = Column(Integer, nullable=True)
    slide_number = Column(Integer, nullable=True)
    time_start = Column(Float, nullable=True)
    time_end = Column(Float, nullable=True)
    image_path = Column(String(1024), nullable=True)
    bounding_box = Column(JSONB, nullable=True)
    sequence_index = Column(Integer, default=0, nullable=False)
    unit_metadata = Column("metadata", JSONB, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    source = relationship("Source", back_populates="content_units")

    __table_args__ = (
        CheckConstraint(
            """(source_type = 'pdf' AND page_number IS NOT NULL AND page_number > 0) OR
               (source_type = 'pptx' AND slide_number IS NOT NULL AND slide_number > 0) OR
               (source_type = 'video' AND time_start IS NOT NULL AND time_end IS NOT NULL AND time_end >= time_start) OR
               (source_type = 'image' AND image_path IS NOT NULL AND length(image_path) > 0)""",
            name="ck_content_unit_provenance_by_source_type"
        ),
    )


# ---------------------------------------------------------------------------
# Phase 1b: users
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Phase 2: knowledge representation
# Embeddings are stored as float arrays and compared with numpy (course-sized corpora).
# This avoids requiring the pgvector extension on native Windows Postgres; swap to a
# pgvector column later if the corpus outgrows in-memory search.
# ---------------------------------------------------------------------------
class Topic(Base):
    __tablename__ = "topics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    sequence = Column(Integer, default=0, nullable=False)


class Concept(Base):
    __tablename__ = "concepts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    key = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    aliases = Column(JSONB, default=list, nullable=False)
    embedding = Column(ARRAY(Float), nullable=True)
    embedding_model = Column(String(100), nullable=True)


class ConceptPrereq(Base):
    __tablename__ = "concept_prereqs"
    __table_args__ = (UniqueConstraint("concept_id", "prereq_id", name="uq_concept_prereq"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    concept_id = Column(UUID(as_uuid=True), ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False, index=True)
    prereq_id = Column(UUID(as_uuid=True), ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False, index=True)


class Chunk(Base):
    """Retrieval unit. Always points back to ContentUnit rows (the single provenance model)."""
    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    primary_unit_id = Column(UUID(as_uuid=True), ForeignKey("content_units.id", ondelete="CASCADE"), nullable=False)
    unit_ids = Column(JSONB, default=list, nullable=False)
    text = Column(Text, nullable=False)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="SET NULL"), nullable=True, index=True)
    concept_id = Column(UUID(as_uuid=True), ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True, index=True)
    embedding = Column(ARRAY(Float), nullable=True)
    embedding_model = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Phase 3: tutor conversations
# ---------------------------------------------------------------------------
class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    messages = relationship("Message", cascade="all, delete-orphan", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    label = Column(String(30), nullable=True)  # GROUNDED | PARTIAL | NOT_COVERED | OUTSIDE_COURSE
    citations = Column(JSONB, default=list, nullable=False)
    meta = Column(JSONB, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Phase 4: assessment + learner model
# ---------------------------------------------------------------------------
class Question(Base):
    __tablename__ = "questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True)
    unit_id = Column(UUID(as_uuid=True), ForeignKey("content_units.id", ondelete="SET NULL"), nullable=True)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)
    concept_id = Column(UUID(as_uuid=True), ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True, index=True)
    qtype = Column(String(20), nullable=False)  # mcq | short | numeric
    stem = Column(Text, nullable=False)
    options = Column(JSONB, nullable=True)  # [{text, is_correct, misconception}]
    answer = Column(Text, nullable=False)
    numeric_expr = Column(Text, nullable=True)
    tolerance = Column(Float, nullable=True)
    explanation = Column(Text, nullable=False)
    difficulty_prior = Column(Float, nullable=False, default=3.0)  # 1..5, LLM guess
    difficulty_est = Column(Float, nullable=False, default=3.0)  # blended with attempt data
    attempts = Column(Integer, default=0, nullable=False)
    correct_count = Column(Integer, default=0, nullable=False)
    verified = Column(Boolean, default=False, nullable=False)
    verification = Column(JSONB, default=dict, nullable=False)
    stem_hash = Column(String(64), nullable=False, index=True)
    embedding = Column(ARRAY(Float), nullable=True)
    embedding_model = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class GenerationAttempt(Base):
    """Every generation attempt (pass or fail) so verification pass-rate is measurable."""
    __tablename__ = "generation_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    passed = Column(Boolean, nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(20), nullable=False, default="quiz")  # quiz | diagnostic | exam
    config = Column(JSONB, default=dict, nullable=False)
    status = Column(String(20), nullable=False, default="in_progress")  # in_progress | completed
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    items = relationship("AssessmentItem", cascade="all, delete-orphan", order_by="AssessmentItem.position")


class AssessmentItem(Base):
    __tablename__ = "assessment_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id = Column(UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, index=True)
    position = Column(Integer, nullable=False)
    option_order = Column(JSONB, nullable=True)  # shuffled indices into Question.options
    user_answer = Column(Text, nullable=True)
    correct = Column(Boolean, nullable=True)
    response_time = Column(Float, nullable=True)
    feedback = Column(JSONB, nullable=True)
    answered_at = Column(DateTime(timezone=True), nullable=True)

    question = relationship("Question")


class Mastery(Base):
    __tablename__ = "mastery"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    concept_id = Column(UUID(as_uuid=True), ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True)
    p_mastery = Column(Float, nullable=False)
    stability_days = Column(Float, nullable=False, default=2.0)
    attempts = Column(Integer, nullable=False, default=0)
    correct = Column(Integer, nullable=False, default=0)
    streak = Column(Integer, nullable=False, default=0)
    prior_source = Column(String(20), nullable=False, default="default")  # default | intake | diagnostic
    last_evidence_at = Column(DateTime(timezone=True), nullable=True)
    last_wrong_at = Column(DateTime(timezone=True), nullable=True)


class EvidenceEvent(Base):
    __tablename__ = "evidence_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    concept_id = Column(UUID(as_uuid=True), ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(20), nullable=False)  # quiz | check | question | intake
    weight = Column(Float, nullable=False)
    correct = Column(Boolean, nullable=True)
    p_before = Column(Float, nullable=False)
    p_after = Column(Float, nullable=False)
    response_time = Column(Float, nullable=True)  # logged only; not used in mastery until validated
    meta = Column(JSONB, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind = Column(String(40), nullable=False)
    config = Column(JSONB, default=dict, nullable=False)
    metrics = Column(JSONB, default=dict, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
