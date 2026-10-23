"""Post-deploy smoke on an isolated synthetic teacher; always remove its data.

Run inside the API container, with the synthetic two-question JPEG at
/tmp/hbj-smoke.jpg. No passwords, tokens or existing user data are printed.
"""
import asyncio
import secrets
from pathlib import Path

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.auth.passwords import hash_password
from app.auth.tokens import issue_token
from app.config import get_settings
from app.db import make_engine
from app.models import Export, Teacher
from app.storage.base import get_storage


async def main():
    s = get_settings()
    engine = make_engine(s.DATABASE_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    login = 'qa_release_' + secrets.token_hex(4)
    password = secrets.token_urlsafe(20)
    ids, class_id = [], None
    headers = {}
    try:
        async with sessions() as db:
            a = Teacher(login_name=login, password_hash=hash_password(password), display_name='发布合成验收', page_quota=s.FREE_MONTHLY_PAGES)
            b = Teacher(display_name='发布隔离验收', page_quota=s.FREE_MONTHLY_PAGES)
            db.add_all([a,b]); await db.commit()
            ids = [a.id,b.id]
            other_token = issue_token(b.id)
        async with httpx.AsyncClient(base_url='http://nginx', timeout=180) as client:
            async def call(method,path,**kw):
                r = await client.request(method,'/api'+path,headers=headers,**kw)
                r.raise_for_status()
                return r.json() if r.content else None
            auth = await call('POST','/auth/login',json={'login_name':login,'password':password})
            headers['Authorization']='Bearer '+auth['token']
            me = await call('GET','/me')
            assert me['quota_total']==s.FREE_MONTHLY_PAGES and me['quota_used']==0
            print('PASS production password login and quota',flush=True)
            room = await call('POST','/classes',json={'name':'发布合成验收（自动清理）','grade':5})
            class_id=room['id']
            roster=await call('POST',f'/classes/{class_id}/students:import',json={'text':'01 验收甲'})
            assert roster['created']==1
            a=await call('POST','/assignments',json={'class_id':class_id,'subject':'math','title':'发布合成验收'})
            aid=a['id']
            await call('PUT',f'/assignments/{aid}/answer-key',json={'items':[{'question_no':'1','answer':'0.72','max_score':5,'is_subjective':False},{'question_no':'2','answer':'0.64','max_score':5,'is_subjective':False}]})
            with Path('/tmp/hbj-smoke.jpg').open('rb') as image:
                await call('POST',f'/assignments/{aid}/pages?source=web',files={'file':('synthetic.jpg',image,'image/jpeg')})
            for _ in range(60):
                progress=await call('GET',f'/assignments/{aid}/progress')
                if progress['failed']: raise AssertionError('production grading failed')
                if progress['done']==1: break
                await asyncio.sleep(3)
            else: raise TimeoutError('production grading timeout')
            subs=await call('GET',f'/assignments/{aid}/submissions')
            assert len(subs)==1 and subs[0]['total_score']==5
            print('PASS production upload, worker, model and score',flush=True)
            detail = await call('GET', f"/submissions/{subs[0]['id']}")
            assert detail['questions']
            for question in detail['questions']:
                assert question['scoring_basis'] and question['guidance']
                if question['score'] < question['max_score']:
                    assert question['error_reason']
            print('PASS production instructional feedback persisted and served', flush=True)
            r=await client.get(f'/api/assignments/{aid}',headers={'Authorization':'Bearer '+other_token})
            assert r.status_code==404
            print('PASS production teacher isolation',flush=True)
            export=await call('POST',f'/assignments/{aid}/exports',json={'kind':'lecture'})
            pdf=await client.get(export['url'])
            assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')
            print('PASS production PDF export',flush=True)
    finally:
        if class_id is not None:
            async with httpx.AsyncClient(base_url='http://nginx',timeout=30) as cleanup:
                r=await cleanup.delete(f'/api/classes/{class_id}',headers=headers)
                r.raise_for_status()
        if ids:
            async with sessions() as db:
                # Exports are not owned by the class; remove their storage objects
                # before the teacher's cascading delete removes the tracking rows.
                exports = (await db.execute(select(Export).where(Export.teacher_id.in_(ids)))).scalars().all()
                storage = get_storage()
                for item in exports:
                    await storage.delete(item.file_key)
                await db.execute(delete(Teacher).where(Teacher.id.in_(ids)))
                await db.commit()
            print('PASS production synthetic data cleaned up',flush=True)
        await engine.dispose()


if __name__=='__main__':
    asyncio.run(main())
