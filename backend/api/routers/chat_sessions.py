"""对话会话管理接口。

GET    /api/v1/sessions              当前用户的会话列表
GET    /api/v1/sessions/{id}/messages 某会话的全部消息（含归属校验）
PATCH  /api/v1/sessions/{id}          重命名会话
DELETE /api/v1/sessions/{id}          删除会话（消息级联删除）
"""
from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_current_user, get_db
from backend.db import chat_repo
from backend.schemas.agent import MessageOut, SessionOut, SessionRenameRequest

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionOut])
def list_sessions(conn=Depends(get_db), current_user=Depends(get_current_user)):
    with conn.cursor() as cur:
        return chat_repo.list_sessions(cur, current_user["id"])


@router.get("/{session_id}/messages", response_model=list[MessageOut])
def get_messages(session_id: int, conn=Depends(get_db), current_user=Depends(get_current_user)):
    with conn.cursor() as cur:
        rows = chat_repo.get_messages(cur, session_id, current_user["id"])
    if rows is None:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")
    return rows


@router.patch("/{session_id}", response_model=SessionOut)
def rename_session(
    session_id: int,
    payload: SessionRenameRequest,
    conn=Depends(get_db),
    current_user=Depends(get_current_user),
):
    with conn.cursor() as cur:
        ok = chat_repo.rename_session(cur, session_id, current_user["id"], payload.title)
        if not ok:
            raise HTTPException(status_code=404, detail="会话不存在或无权访问")
        conn.commit()
        cur.execute(
            "SELECT id, title, created_at, updated_at FROM chat_sessions WHERE id = %s",
            (session_id,),
        )
        return cur.fetchone()


@router.delete("/{session_id}")
def delete_session(session_id: int, conn=Depends(get_db), current_user=Depends(get_current_user)):
    with conn.cursor() as cur:
        ok = chat_repo.delete_session(cur, session_id, current_user["id"])
        if not ok:
            raise HTTPException(status_code=404, detail="会话不存在或无权访问")
        conn.commit()
    return {"ok": True}
