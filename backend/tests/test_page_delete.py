from sqlalchemy import func, select

from app.models import Page, PageStatus, QuestionResult, Student, Submission
from app.quota.service import pages_used_this_month
from tests.conftest import count_results, graded, make_result, q, storage_exists


async def test_delete_done_page_recomputes_submission(db, auth_client, storage, graded_submission, make_done_page):
    # a second page of the same student keeps the submission alive
    page2 = await make_done_page(11, graded_submission.student_id, "张三")
    db.add(make_result(page2.id, graded_submission.id, "3", score=3, max_score=3))
    await db.commit()
    page1_id, key1 = graded_submission.page.id, graded_submission.page.image_key
    r = await auth_client.delete(f"/api/pages/{page1_id}")
    assert r.status_code == 204
    db.expire_all()
    assert await db.get(Page, page1_id) is None
    assert await count_results(db, page1_id) == 0
    assert not await storage_exists(storage, key1)
    sub = await db.get(Submission, graded_submission.id)
    assert sub is not None and sub.total_score == 3


async def test_delete_last_page_removes_empty_submission(db, auth_client, storage, graded_submission):
    r = await auth_client.delete(f"/api/pages/{graded_submission.page.id}")
    assert r.status_code == 204
    db.expire_all()
    assert await db.get(Submission, graded_submission.id) is None


async def test_delete_page_removes_images_and_allows_reupload(
        db, auth_client, storage, my_assignment, jpeg_bytes, enqueued, teacher):
    url = f"/api/assignments/{my_assignment.id}/pages"
    first = (await auth_client.post(url, files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})).json()
    page_id = first["page_id"]
    key = f"originals/{teacher.id}/{my_assignment.id}/{page_id}.jpg"
    crop = f"crops/{teacher.id}/{my_assignment.id}/c1.jpg"
    await storage.put(crop, b"x", "image/jpeg")
    db.add(make_result(page_id, None, "1", crop_key=crop))
    await db.commit()
    assert (await auth_client.delete(f"/api/pages/{page_id}")).status_code == 204
    assert not await storage_exists(storage, key)
    assert not await storage_exists(storage, crop)
    again = await auth_client.post(url, files={"file": ("a.jpg", jpeg_bytes, "image/jpeg")})
    assert again.status_code == 201 and again.json()["duplicate"] is False


async def test_delete_page_with_missing_files_still_succeeds(db, auth_client, storage, unmatched_page):
    await storage.delete(unmatched_page.image_key)
    r = await auth_client.delete(f"/api/pages/{unmatched_page.id}")
    assert r.status_code == 204


async def test_delete_queued_page_then_job_is_noop(db, auth_client, storage, make_page):
    from app.ai.fake import FakeModel
    from app.grading.pipeline import grade_page

    page = await make_page(1)
    page_id = page.id
    assert (await auth_client.delete(f"/api/pages/{page_id}")).status_code == 204
    await db.rollback()
    model = FakeModel([graded(student_name="张三", questions=[q(no="1")])])
    await grade_page(db, storage, model, page_id)  # must not raise
    assert await count_results(db, page_id) == 0
    assert (await db.execute(select(func.count()).select_from(Page))).scalar_one() == 0


async def test_delete_other_teachers_page_404(auth_client, other_teacher_failed_page):
    r = await auth_client.delete(f"/api/pages/{other_teacher_failed_page.id}")
    assert r.status_code == 404


async def test_delete_unknown_page_404(auth_client):
    assert (await auth_client.delete("/api/pages/999999")).status_code == 404


async def test_delete_does_not_refund_quota(db, auth_client, storage, teacher, make_page):
    tid = teacher.id
    p1, p2 = await make_page(1), await make_page(2)
    assert await pages_used_this_month(db, tid) == 2
    assert (await auth_client.delete(f"/api/pages/{p1.id}")).status_code == 204
    assert await pages_used_this_month(db, tid) == 2
    assert (await auth_client.delete(f"/api/pages/{p2.id}")).status_code == 204
    assert await pages_used_this_month(db, tid) == 2
