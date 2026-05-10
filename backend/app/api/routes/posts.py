"""YuQing Poster API routes."""

from fastapi import APIRouter

from app.core.poster import poster_engine

router = APIRouter()


@router.get("/posts")
async def list_posts(limit: int = 30):
    """List recent posts, newest first."""
    posts = await poster_engine.get_posts(limit=limit)
    return {"ok": True, "count": len(posts), "posts": posts}


@router.post("/posts/generate")
async def generate_post():
    """Manually trigger a new post generation (force mode)."""
    post = await poster_engine.generate_daily_post(force=True)
    if post:
        return {"ok": True, "post": post}
    return {"ok": False, "error": "Generation failed"}
