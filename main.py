from fastapi import FastAPI
from routers.users import router as users_router
from routers.groups import router as groups_router
from routers.expenses import router as expenses_router


app=FastAPI(title="Expense Tracker")

app.include_router(users_router)
app.include_router(groups_router)
app.include_router(expenses_router)

@app.get("/health")
def health_check():
    return {"status":"Ok"}