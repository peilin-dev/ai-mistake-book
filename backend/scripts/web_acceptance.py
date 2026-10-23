"""Real-model acceptance on a dedicated synthetic LOCAL teacher and class.

Run from backend/: python scripts/web_acceptance.py
All run state (including temporary credentials) stays in ignored storage/acceptance.
Never run this against the production database; production smoke checks are read-only.
"""
import asyncio
import json
import secrets
import sys
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.auth.passwords import hash_password
from app.auth.tokens import issue_token
from app.config import get_settings
from app.db import make_engine
from app.models import Teacher

ROOT = Path('storage/acceptance')
ROOT.mkdir(parents=True, exist_ok=True)
STATE = ROOT / 'run.json'
REPORT = ROOT / 'report.json'
BASE = 'http://127.0.0.1:5175'


def note(message):
    print(message, flush=True)


def sheet(name, heading, lines):
    image = Image.new('RGB', (1400, 1800), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 48)
    small = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 32)
    draw.text((90, 65), '五年级数学 · 小数乘法验收练习', font=font, fill='black')
    draw.text((90, 150), heading, font=font, fill='black')
    draw.text((90, 235), '以下每题满分 5 分，请核对算式及答案。', font=small, fill='black')
    for i, line in enumerate(lines):
        y = 380 + i * 290
        draw.text((100, y), line, font=font, fill='black')
        draw.line((90, y + 200, 1310, y + 200), fill='#aaaaaa', width=2)
    path = ROOT / name
    image.save(path, quality=90)
    return path


async def provision():
    s = get_settings()
    assert 'localhost' in s.DATABASE_URL or '127.0.0.1' in s.DATABASE_URL, 'local database required'
    engine = make_engine(s.DATABASE_URL)
    password = secrets.token_urlsafe(18)
    login = 'qa_web_' + time.strftime('%m%d') + '_' + secrets.token_hex(3)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        teacher = Teacher(login_name=login, password_hash=hash_password(password), display_name='网页合成验收', page_quota=100)
        other = Teacher(display_name='隔离验收', page_quota=30)
        db.add_all([teacher, other])
        await db.commit()
        state = dict(login=login, password=password, teacher_id=teacher.id, token=issue_token(teacher.id), other_id=other.id, other_token=issue_token(other.id))
    await engine.dispose()
    STATE.write_text(json.dumps(state), encoding='utf-8')
    return state


def main():
    resume = '--resume' in sys.argv and STATE.exists()
    state = json.loads(STATE.read_text(encoding='utf-8')) if resume else asyncio.run(provision())
    report = {'checks': [], 'started_at': time.strftime('%Y-%m-%d %H:%M:%S')}
    def check(label, condition):
        if not condition:
            raise AssertionError(label)
        report['checks'].append(label)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        note('PASS ' + label)
    with httpx.Client(base_url=BASE, timeout=180) as client:
        def call(method, path, **kw):
            response = client.request(method, '/api' + path, **kw)
            if response.status_code >= 400:
                raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:300]}')
            return response.json() if response.content else None
        login = call('POST', '/auth/login', json={'login_name':state['login'], 'password':state['password']})
        check('password_login', bool(login.get('token')))
        client.headers['Authorization'] = 'Bearer ' + login['token']
        me = call('GET', '/me')
        check('profile_quota', me['quota_total'] == 100)
        room = next((c for c in call('GET','/classes') if c['id']==state.get('class_id')),None) if resume else None
        room = room or call('POST', '/classes', json={'name':'网页真实验收（合成班级）','grade':5})
        state['class_id'] = room['id']
        roster = call('POST', f"/classes/{room['id']}/students:import", json={'text':'01 验收甲\n02 验收乙\n03 验收丙'})
        check('class_and_roster', len(roster['students']) == 3)
        students = {s['name']:s['id'] for s in roster['students']}
        a = call('GET',f"/assignments/{state['assignment_id']}") if resume and state.get('assignment_id') else call('POST','/assignments',json={'class_id':room['id'],'subject':'math','title':'小数乘法真实验收（合成）'})
        aid = a['id']; state['assignment_id'] = aid
        STATE.write_text(json.dumps(state),encoding='utf-8')
        check('create_assignment', a['subject'] == 'math')
        key = sheet('answer-key.jpg','标准答案卷（合成样本）',['1. 2.4 × 0.3 = 0.72','2. 1.6 × 0.4 = 0.64','3. 2.8 × 1.5 = 4.2','4. 3.2 × 0.5 = 1.6'])
        note('RUN real answer-key extraction')
        extracted = call('GET',f'/assignments/{aid}/answer-key') if resume else None
        if not extracted or len(extracted['items']) != 4:
            with key.open('rb') as f:
                extracted = call('POST',f'/assignments/{aid}/answer-key',files={'file':(key.name,f,'image/jpeg')})
        check('real_answer_key_extraction', {i['question_no'] for i in extracted['items']} == {'1','2','3','4'})
        expected = dict(zip(['1','2','3','4'],['0.72','0.64','4.2','1.6']))
        check('answer_key_values', all(i['answer'].rsplit('=',1)[-1].strip() == expected[i['question_no']] and i['max_score'] == 5 for i in extracted['items']))
        # The model legitimately copies the full printed equation. A teacher
        # checks it and edits the answer cell down to its numeric result.
        for item in extracted['items']:
            item['answer'] = expected[item['question_no']]
        confirmed = call('PUT',f'/assignments/{aid}/answer-key',json={'items':extracted['items']})
        check('answer_key_confirm', confirmed['answer_key_status'] == 'confirmed')
        files = [
            sheet('student-a.jpg','姓名：验收甲',['1. 2.4 × 0.3 = 7.2','2. 1.6 × 0.4 = 0.64']),
            sheet('student-a-back.jpg','试卷背面（没有填写姓名）',['3. 2.8 × 1.5 = 42','4. 3.2 × 0.5 = 1.6']),
            sheet('student-b.jpg','姓名：验收乙',['1. 2.4 × 0.3 = 0.72','2. 1.6 × 0.4 = 0.64','3. 2.8 × 1.5 = 4.2','4. 3.2 × 0.5 = 1.6']),
        ]
        uploaded = []
        for path in files:
            with path.open('rb') as f:
                uploaded.append(call('POST',f'/assignments/{aid}/pages?source=web',files={'file':(path.name,f,'image/jpeg')}))
        check('real_uploads', len({p['page_id'] for p in uploaded}) == 3)
        with files[0].open('rb') as f:
            duplicate = call('POST',f'/assignments/{aid}/pages?source=web',files={'file':('duplicate.jpg',f,'image/jpeg')})
        check('duplicate_no_extra_quota', duplicate['duplicate'] and call('GET','/me')['quota_used'] == 3)
        deadline = time.monotonic() + 480
        while time.monotonic() < deadline:
            progress = call('GET',f'/assignments/{aid}/progress')
            note('GRADING ' + json.dumps(progress))
            if progress['failed']:
                raise AssertionError('grading failed: ' + str(call('GET',f'/assignments/{aid}/pages')))
            if progress['done'] == 3: break
            time.sleep(4)
        else: raise TimeoutError('grading timeout')
        check('real_grading_worker', progress['done'] == 3)
        pages = call('GET',f'/assignments/{aid}/pages')
        check('web_source', all(p['source'] == 'web' for p in pages))
        back = next(p for p in pages if p['page_id'] == uploaded[1]['page_id'])
        check('nameless_web_page_not_chained', back['student_id'] is None)
        candidates = call('GET',f"/pages/{back['page_id']}/claim-candidates")
        check('claim_candidates_order', candidates['candidates'][0]['student_id'] == students['验收甲'])
        call('PATCH',f"/pages/{back['page_id']}",json={'student_id':students['验收甲']})
        queue = call('GET',f'/assignments/{aid}/review')
        check('claim_clears_unassigned', not queue['pages_unassigned'])
        subs = call('GET',f'/assignments/{aid}/submissions')
        check('two_student_submissions', len(subs) == 2)
        sub = next(s for s in subs if s['student_id'] == students['验收甲'])
        state['submission_id'] = sub['id']; STATE.write_text(json.dumps(state),encoding='utf-8')
        detail = call('GET',f"/submissions/{sub['id']}")
        check('scores_and_merged_pages', detail['total_score'] == 10 and len(detail['questions']) == 4)
        wrong = next(q for q in detail['questions'] if q['question_no'] == '1')
        call('PATCH',f"/question-results/{wrong['id']}",json={'score':2.5})
        check('correction_recomputes_score', call('GET',f"/submissions/{sub['id']}")['total_score'] == 12.5)
        call('PATCH',f"/question-results/{wrong['id']}",json={'score':0,'is_correct':False})
        analytics = call('GET',f'/assignments/{aid}/analytics')
        check('analytics_updates', analytics['counted_students'] == 2 and analytics['roster_size'] == 3 and analytics['average_score'] == 15)
        history = call('GET',f"/submissions/{sub['id']}/history")
        check('student_history', bool(history) and history[0]['score'] == 10)
        other = {'Authorization':'Bearer ' + state['other_token']}
        for path in [f'/assignments/{aid}',f'/classes/{room["id"]}/students',f'/pages/{back["page_id"]}/claim-candidates',f'/submissions/{sub["id"]}']:
            check('teacher_isolation:' + path, client.get('/api'+path,headers=other).status_code == 404)
        # Clear outstanding review items exactly as a teacher confirms original judgments.
        for q in queue['questions']:
            call('PATCH',f"/question-results/{q['id']}",json={'score':q['score'],'is_correct':q['is_correct']})
        check('review_queue_completed', not call('GET',f'/assignments/{aid}/review')['questions'])
        note('RUN real learning summary')
        summary = call('POST',f"/submissions/{sub['id']}/summary")
        check('real_learning_summary', bool(summary['summary']))
        def paper(scope):
            note('RUN real practice: ' + scope)
            p = call('POST',scope+'/practice')
            deadline = time.monotonic() + 360
            while time.monotonic() < deadline:
                p = call('GET',scope+'/practice')
                note('PRACTICE ' + json.dumps({k:p[k] for k in ['id','status','sources_total','sources_done','partial']}))
                if p['status'] == 'failed': raise AssertionError('practice failed: '+str(p['error']))
                if p['status'] == 'done': break
                time.sleep(4)
            else: raise TimeoutError('practice timeout')
            check('practice_done:'+scope, bool(p['items']) and not p['partial'])
            return p
        class_paper = paper(f'/assignments/{aid}')
        paper(f"/submissions/{sub['id']}")
        item = class_paper['items'][0]
        call('POST',f"/practice-items/{item['id']}/replace")
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            p=call('GET',f'/assignments/{aid}/practice')
            if not any(i['replacing'] for i in p['items']): break
            time.sleep(3)
        check('practice_replace', p['last_replace_failed_item'] is None and next(i for i in p['items'] if i['id']==item['id'])['stem'] != item['stem'])
        from pypdf import PdfReader
        for kind in ['lecture','class_students','student','practice','practice_student']:
            out = call('POST',f'/assignments/{aid}/exports',json={'kind':kind,'submission_id':sub['id'],'include_answers':True})
            result = client.get(out['url']); result.raise_for_status()
            path = ROOT / (kind+'.pdf'); path.write_bytes(result.content)
            reader = PdfReader(path)
            check('pdf_export:'+kind, len(reader.pages)>0 and '网页合成验收' in ''.join(p.extract_text() for p in reader.pages))
        report['completed_at']=time.strftime('%Y-%m-%d %H:%M:%S')
        report['assignment_id']=aid
        REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        note('COMPLETE ' + str(len(report['checks'])) + ' acceptance checks')


if __name__ == '__main__':
    main()
