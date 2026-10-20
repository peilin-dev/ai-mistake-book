import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import (
    AnswerKeyStatus,
    Class_,
    Page,
    PageStatus,
    QuestionResult,
    Student,
    Submission,
    Teacher,
)


async def test_page_sha_unique_per_assignment(db, make_assignment):
    a = await make_assignment()
    db.add(Page(assignment_id=a.id, seq=1, image_key="k1", image_sha256="x"))
    await db.commit()
    db.add(Page(assignment_id=a.id, seq=2, image_key="k2", image_sha256="x"))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


async def test_same_sha_allowed_across_assignments(db, make_assignment):
    a1 = await make_assignment()
    a2 = await make_assignment()
    db.add(Page(assignment_id=a1.id, seq=1, image_key="k1", image_sha256="x"))
    db.add(Page(assignment_id=a2.id, seq=1, image_key="k2", image_sha256="x"))
    await db.commit()


async def test_defaults_and_timestamps(db, make_assignment):
    a = await make_assignment()
    assert a.answer_key_status == AnswerKeyStatus.none
    assert a.created_at is not None and a.updated_at is not None
    p = Page(assignment_id=a.id, seq=1, image_key="k", image_sha256="s")
    db.add(p)
    await db.commit()
    assert p.status == PageStatus.queued
    raw = (await db.execute(text("select status from pages"))).scalar_one()
    assert raw == "queued"  # stored as VARCHAR


async def test_teacher_unionid_and_openid_unique(db):
    db.add(Teacher(unionid="u", mp_openid="o1"))
    await db.commit()
    db.add(Teacher(unionid="u", mp_openid="o2"))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()
    db.add(Teacher(unionid="u2", mp_openid="o1"))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


async def test_submission_unique_per_student(db, make_assignment):
    a = await make_assignment()
    cls = (await db.execute(select(Class_))).scalars().first()
    s = Student(class_id=cls.id, name="张三")
    db.add(s)
    await db.commit()
    db.add(Submission(assignment_id=a.id, student_id=s.id))
    await db.commit()
    db.add(Submission(assignment_id=a.id, student_id=s.id))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


async def test_question_result_submission_nullable_page_required(db, make_assignment):
    a = await make_assignment()
    p = Page(assignment_id=a.id, seq=1, image_key="k", image_sha256="s")
    db.add(p)
    await db.commit()
    qr = QuestionResult(page_id=p.id, question_no="1", model_is_correct=None, model_score=None)
    db.add(qr)
    await db.commit()
    assert qr.submission_id is None
    db.add(QuestionResult(question_no="2"))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()


async def test_delete_class_cascades(db, make_assignment):
    a = await make_assignment()
    p = Page(assignment_id=a.id, seq=1, image_key="k", image_sha256="s")
    db.add(p)
    await db.commit()
    await db.execute(text("delete from classes"))
    await db.commit()
    assert (await db.execute(text("select count(*) from pages"))).scalar_one() == 0
    assert (await db.execute(text("select count(*) from assignments"))).scalar_one() == 0
