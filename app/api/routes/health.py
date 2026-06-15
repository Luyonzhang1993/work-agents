from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/")
async def root() -> dict[str, str]:
    return {"message": "work-agents API is running"}


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
