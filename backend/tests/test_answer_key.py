import pytest
from sqlalchemy import func, select

from app.ai.base import ModelCallError, ModelOutputError
from app.models import AnswerItem, AnswerKeyStatus, Page, PageStatus, UsageRecord


def key_url(assignment) -> str:
    return f"/api/assignments/{assignment.id}/answer-key"


def photo(jpeg_bytes):
    return {"file": ("k.jpg", jpeg_bytes, "image/jpeg")}


async def usage_count(db) -> int:
    return (await db.execute(select(func.count()).select_from(UsageRecord).where(
        UsageRecord.purpose == "answer_key"))).scalar_one()


async def item_rows(db, assignment) -> list[AnswerItem]:
    stmt = (
        select(AnswerItem)
        .where(AnswerItem.assignment_id == assignment.id)
        .order_by(AnswerItem.id)
        .execution_options(populate_existing=True)
    )
    return list((await db.execute(stmt)).scalars())


async def test_extract_then_confirm(auth_client, my_assignment, jpeg_bytes, fake_model_answer_key):
    url = key_url(my_assignment)
    items = (await auth_client.post(url, files=photo(jpeg_bytes))).json()["items"]
    assert items[0]["question_no"] == "1"
    items[0]["answer"] = "62.8dm³"
    r = await auth_client.put(url, json={"items": items})
    assert r.json()["answer_key_status"] == "confirmed"


async def test_post_stores_items_pending_and_returns_in_order(
    auth_client, db, my_assignment, jpeg_bytes, fake_model_answer_key
):
    r = await auth_client.post(key_url(my_assignment), files=photo(jpeg_bytes))
    assert r.status_code == 200
    body = r.json()
    assert body["answer_key_status"] == "pending"
    assert body["items"] == [
        {"question_no": "1", "answer": "7", "max_score": 2.0, "is_subjective": False},
        {"question_no": "2", "answer": "12", "max_score": 4.0, "is_subjective": False},
    ]
    await db.refresh(my_assignment)
    assert my_assignment.answer_key_status == AnswerKeyStatus.pending
    assert [i.question_no for i in await item_rows(db, my_assignment)] == ["1", "2"]
    assert await usage_count(db) == 1
    assert "标准答案" in fake_model_answer_key.prompts[0]


async def test_post_does_not_store_photo_or_use_quota(
    auth_client, db, my_assignment, jpeg_bytes, fake_model_answer_key, storage, settings
):
    await auth_client.post(key_url(my_assignment), files=photo(jpeg_bytes))
    assert not [p for p in storage.root.rglob("*") if p.is_file()]
    assert (await db.execute(select(func.count()).select_from(Page))).scalar_one() == 0


async def test_question_no_coerced_to_str(auth_client, my_assignment, jpeg_bytes, install_answer_key_model):
    install_answer_key_model([{"questions": [{"question_no": 3, "answer": "x", "max_score": 1}]}])
    r = await auth_client.post(key_url(my_assignment), files=photo(jpeg_bytes))
    assert r.json()["items"][0] == {"question_no": "3", "answer": "x", "max_score": 1.0, "is_subjective": False}


async def test_bad_output_retried_once_then_ok(
    auth_client, db, my_assignment, jpeg_bytes, install_answer_key_model
):
    model = install_answer_key_model([
        ModelOutputError("not json"),
        {"questions": [{"question_no": "1", "answer": "a", "max_score": 1}]},
    ])
    r = await auth_client.post(key_url(my_assignment), files=photo(jpeg_bytes))
    assert r.status_code == 200
    assert len(model.prompts) == 2


async def test_two_bad_outputs_give_502_and_usage_is_kept(
    auth_client, db, my_assignment, jpeg_bytes, install_answer_key_model
):
    bad = {"questions": [{"question_no": "", "answer": "a", "max_score": 1}]}
    model = install_answer_key_model([bad, bad])
    r = await auth_client.post(key_url(my_assignment), files=photo(jpeg_bytes))
    assert r.status_code == 502
    assert r.json()["detail"] == "答案卷识别失败，请重拍"
    assert len(model.prompts) == 2
    await db.rollback()  # only committed rows survive
    assert await usage_count(db) == 2
    assert await item_rows(db, my_assignment) == []


async def test_model_call_error_gives_503(auth_client, my_assignment, jpeg_bytes, install_answer_key_model):
    install_answer_key_model([ModelCallError("down")])
    r = await auth_client.post(key_url(my_assignment), files=photo(jpeg_bytes))
    assert r.status_code == 503
    assert r.json()["detail"] == "批改服务暂不可用，请稍后重试"


async def test_answer_key_survives_a_flaky_connection(app, auth_client, my_assignment, jpeg_bytes, mock_transport):
    # The real adapter (not FakeModel): a dropped connection is retried inside the call,
    # so the teacher gets the extracted key instead of "批改服务暂不可用".
    import json

    import httpx

    from app.ai.openai_compat import OpenAICompatModel
    from app.grading.answer_key import get_answer_key_model

    content = json.dumps({"questions": [{"question_no": "1", "answer": "7", "max_score": 2}]})
    mock_transport.fail(httpx.ConnectTimeout("handshake timed out"))
    mock_transport.reply({"choices": [{"message": {"content": content}}]})
    model = OpenAICompatModel("qwen", "https://x/v1", "k", "m", transport=mock_transport, retry_backoff=0)
    app.dependency_overrides[get_answer_key_model] = lambda: model
    r = await auth_client.post(key_url(my_assignment), files=photo(jpeg_bytes))
    assert r.status_code == 200
    assert [i["question_no"] for i in r.json()["items"]] == ["1"]
    assert len(mock_transport.requests) == 2


async def test_zero_questions_gives_422_and_keeps_old_key(
    auth_client, db, my_assignment, jpeg_bytes, install_answer_key_model, confirmed_key_q1_q2
):
    install_answer_key_model([{"questions": []}])
    r = await auth_client.post(key_url(my_assignment), files=photo(jpeg_bytes))
    assert r.status_code == 422
    assert r.json()["detail"] == "未识别到题目"
    await db.rollback()
    assert await usage_count(db) == 1
    assert len(await item_rows(db, my_assignment)) == 2
    await db.refresh(my_assignment)
    assert my_assignment.answer_key_status == AnswerKeyStatus.confirmed


async def test_non_image_gives_415(auth_client, my_assignment, fake_model_answer_key):
    r = await auth_client.post(key_url(my_assignment), files={"file": ("k.jpg", b"not an image", "image/jpeg")})
    assert r.status_code == 415
    assert fake_model_answer_key.prompts == []


async def test_repost_after_confirm_replaces_items_and_resets_to_pending(
    auth_client, db, my_assignment, jpeg_bytes, install_answer_key_model, confirmed_key_q1_q2
):
    install_answer_key_model([{"questions": [{"question_no": "9", "answer": "z", "max_score": 3}]}])
    r = await auth_client.post(key_url(my_assignment), files=photo(jpeg_bytes))
    assert r.json()["answer_key_status"] == "pending"
    assert [i.question_no for i in await item_rows(db, my_assignment)] == ["9"]
    await db.refresh(my_assignment)
    assert my_assignment.answer_key_status == AnswerKeyStatus.pending


async def test_get_returns_status_and_items(auth_client, my_assignment, confirmed_key_q1_q2):
    r = await auth_client.get(key_url(my_assignment))
    assert r.status_code == 200
    body = r.json()
    assert body["answer_key_status"] == "confirmed"
    assert [i["question_no"] for i in body["items"]] == ["1", "2"]


async def test_get_without_key(auth_client, my_assignment):
    r = await auth_client.get(key_url(my_assignment))
    assert r.json() == {"answer_key_status": "none", "items": []}


async def test_put_replaces_items(auth_client, db, my_assignment, confirmed_key_q1_q2):
    items = [{"question_no": "5", "answer": "x", "max_score": 1.5, "is_subjective": True}]
    r = await auth_client.put(key_url(my_assignment), json={"items": items})
    assert r.status_code == 200
    assert r.json() == {"answer_key_status": "confirmed", "items": items, "regrade_suggested": False}
    rows = await item_rows(db, my_assignment)
    assert [(i.question_no, i.is_subjective) for i in rows] == [("5", True)]


@pytest.mark.parametrize("items", [
    [{"question_no": "1", "answer": "a", "max_score": 1}, {"question_no": "1", "answer": "b", "max_score": 1}],
    [{"question_no": "  ", "answer": "a", "max_score": 1}],
    [{"question_no": "1", "answer": "a", "max_score": -1}],
])
async def test_put_invalid_items_gives_422(auth_client, db, my_assignment, confirmed_key_q1_q2, items):
    r = await auth_client.put(key_url(my_assignment), json={"items": items})
    assert r.status_code == 422
    assert len(await item_rows(db, my_assignment)) == 2  # untouched


async def test_regrade_suggested_when_done_page_exists(auth_client, db, my_assignment):
    db.add(Page(assignment_id=my_assignment.id, seq=1, image_key="k", image_sha256="s", status=PageStatus.done))
    await db.commit()
    r = await auth_client.put(
        key_url(my_assignment), json={"items": [{"question_no": "1", "answer": "a", "max_score": 1}]}
    )
    assert r.json()["regrade_suggested"] is True


async def test_regrade_not_suggested_for_unfinished_pages(auth_client, db, my_assignment):
    db.add(Page(assignment_id=my_assignment.id, seq=1, image_key="k", image_sha256="s", status=PageStatus.queued))
    await db.commit()
    r = await auth_client.put(
        key_url(my_assignment), json={"items": [{"question_no": "1", "answer": "a", "max_score": 1}]}
    )
    assert r.json()["regrade_suggested"] is False


async def test_foreign_assignment_is_404(client_for, make_teacher, my_assignment, jpeg_bytes, fake_model_answer_key):
    intruder = client_for(await make_teacher())
    url = key_url(my_assignment)
    assert (await intruder.post(url, files=photo(jpeg_bytes))).status_code == 404
    assert (await intruder.get(url)).status_code == 404
    item = {"question_no": "1", "answer": "a", "max_score": 1}
    assert (await intruder.put(url, json={"items": [item]})).status_code == 404
    assert fake_model_answer_key.prompts == []


async def test_missing_assignment_is_404(auth_client, jpeg_bytes, fake_model_answer_key):
    assert (await auth_client.get("/api/assignments/999999/answer-key")).status_code == 404


# --- final review fix 1: keys without printed scores ---

def test_answer_key_prompt_asks_null_for_unprinted_score():
    from app.grading.prompts import build_answer_key_prompt

    prompt = build_answer_key_prompt()
    assert "填 0" not in prompt
    assert "没有标注时填 null" in prompt


async def test_extracted_key_keeps_null_max_score(auth_client, db, my_assignment, jpeg_bytes,
                                                  install_answer_key_model):
    install_answer_key_model([{"questions": [{"question_no": "1", "answer": "7", "max_score": None}]}])
    r = await auth_client.post(key_url(my_assignment), files=photo(jpeg_bytes))
    assert r.status_code == 200 and r.json()["items"][0]["max_score"] is None
    assert (await item_rows(db, my_assignment))[0].max_score is None


async def test_confirmed_key_without_score_uses_model_max(auth_client, db, storage, my_assignment,
                                                          uploaded_page, roster_zhangsan):
    from app.ai.fake import FakeModel
    from app.grading.pipeline import grade_page
    from app.models import QuestionResult
    from tests.conftest import graded, q

    items = [{"question_no": "1", "answer": "7", "max_score": None, "is_subjective": False}]
    r = await auth_client.put(key_url(my_assignment), json={"items": items})
    assert r.status_code == 200 and r.json()["items"] == items
    assert (await item_rows(db, my_assignment))[0].max_score is None
    got = (await auth_client.get(key_url(my_assignment))).json()
    assert got["items"][0]["max_score"] is None

    page_id = uploaded_page.id
    await db.rollback()
    model = FakeModel([graded(student_name="张三", questions=[q(no="1", score=3, max_score=5)])])
    await grade_page(db, storage, model, page_id)
    res = (await db.execute(select(QuestionResult).execution_options(populate_existing=True))).scalar_one()
    assert (res.score, res.max_score, res.answer_verified) == (3, 5, True)
    r = await auth_client.patch(f"/api/question-results/{res.id}", json={"is_correct": True})
    assert r.status_code == 200 and r.json()["score"] == 5

