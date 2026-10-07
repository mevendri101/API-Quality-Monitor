import asyncio

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

app = FastAPI(title="Demo Shop API")


class User(BaseModel):
    name: str = Field(min_length=1)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/products")
def products():
    return [{"id": 1, "name": "Keyboard", "price": 49}]


@app.post("/users", status_code=201)
def create_user(user: User):
    return {"id": 1, "name": user.name}


@app.get("/private")
def private(authorization: str | None = Header(default=None)):
    if authorization != "Bearer demo-token":
        raise HTTPException(401, "Unauthorized")
    return {"access": "granted"}


@app.get("/broken/status", status_code=202)
def wrong_status():
    return {"status": "created"}


@app.get("/broken/schema")
def wrong_schema():
    return {"name": "Missing ID"}


@app.get("/broken/slow")
async def slow():
    await asyncio.sleep(0.15)
    return {"status": "ok"}


@app.get("/text")
def plain_text():
    return Response("hello", media_type="text/plain")
