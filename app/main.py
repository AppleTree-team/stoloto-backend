from fastapi import FastAPI
import uvicorn

app = FastAPI()


# --------------------
# TEST ROUTE
# --------------------
@app.get("/")
def root():
    return {"status": "ok"}


# --------------------
# RUN SERVER
# --------------------
if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)