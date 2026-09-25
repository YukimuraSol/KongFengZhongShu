from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.equip.search_impl_rev import SEARCH_IMPL_REV

from .routes.calc import router as calc_router
from .routes.equip import router as equip_router
from .routes.settings import router as settings_router

app = FastAPI(title="控分中枢 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(calc_router)
app.include_router(equip_router)
app.include_router(settings_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "search_impl_rev": SEARCH_IMPL_REV}
