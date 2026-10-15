from fastapi import FastAPI

app=FastAPI(title="Expense Tracker")

@app.get("/health")
def health_check():
    return {"status":"Ok"}