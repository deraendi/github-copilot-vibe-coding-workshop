import os
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.openapi.docs import get_swagger_ui_html
from pydantic import BaseModel, Field
from typing import List, Optional
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "sns_api.db")
OPENAPI_PATH = os.path.join(os.path.dirname(__file__), "../openapi.yaml")

app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)

# Enable CORS from everywhere
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    # Posts table
    c.execute("""
    CREATE TABLE IF NOT EXISTS posts (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        content TEXT NOT NULL,
        createdAt TEXT NOT NULL,
        updatedAt TEXT NOT NULL
    )
    """)
    # Comments table
    c.execute("""
    CREATE TABLE IF NOT EXISTS comments (
        id TEXT PRIMARY KEY,
        postId TEXT NOT NULL,
        username TEXT NOT NULL,
        content TEXT NOT NULL,
        createdAt TEXT NOT NULL,
        updatedAt TEXT NOT NULL
    )
    """)
    # Likes table
    c.execute("""
    CREATE TABLE IF NOT EXISTS likes (
        postId TEXT NOT NULL,
        username TEXT NOT NULL,
        PRIMARY KEY (postId, username)
    )
    """)
    conn.commit()
    conn.close()

@app.on_event("startup")
def startup_event():
    init_db()

# Serve Swagger UI at default endpoint
@app.get("/", include_in_schema=False)
def swagger_ui():
    return get_swagger_ui_html(openapi_url="/openapi.yaml", title="Simple Social Media Application API")

# Serve exact OpenAPI YAML at default endpoint
@app.get("/openapi.yaml", include_in_schema=False)
def openapi_yaml():
    return FileResponse(OPENAPI_PATH, media_type="application/yaml")

# ...existing code for endpoints will be added here...
# --- Pydantic Models ---
class Post(BaseModel):
    id: str
    username: str
    content: str
    createdAt: str
    updatedAt: str
    likes: int
    comments: int

class PostCreate(BaseModel):
    username: str
    content: str

class PostUpdate(BaseModel):
    username: str
    content: str

class Comment(BaseModel):
    id: str
    postId: str
    username: str
    content: str
    createdAt: str
    updatedAt: str

class CommentCreate(BaseModel):
    username: str
    content: str

class CommentUpdate(BaseModel):
    username: str
    content: str

class LikeCreate(BaseModel):
    username: str

class LikeDelete(BaseModel):
    username: str

class Error(BaseModel):
    message: str
    code: int

# --- Utility Functions ---
def error_response(message: str, code: int):
    return JSONResponse(status_code=code, content={"message": message, "code": code})

# --- Endpoints ---
# List Posts
@app.get("/posts", response_model=List[Post])
def list_posts():
    conn = get_db()
    c = conn.cursor()
    posts = c.execute("SELECT * FROM posts").fetchall()
    result = []
    for post in posts:
        post_id = post["id"]
        likes = c.execute("SELECT COUNT(*) FROM likes WHERE postId=?", (post_id,)).fetchone()[0]
        comments = c.execute("SELECT COUNT(*) FROM comments WHERE postId=?", (post_id,)).fetchone()[0]
        result.append(Post(**dict(post), likes=likes, comments=comments))
    conn.close()
    return result

# Create Post
@app.post("/posts", response_model=Post, status_code=201)
def create_post(data: PostCreate):
    conn = get_db()
    c = conn.cursor()
    post_id = os.urandom(8).hex()
    now = datetime.utcnow().isoformat()
    try:
        c.execute("INSERT INTO posts (id, username, content, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?)",
                  (post_id, data.username, data.content, now, now))
        conn.commit()
        likes = 0
        comments = 0
        post = Post(id=post_id, username=data.username, content=data.content, createdAt=now, updatedAt=now, likes=likes, comments=comments)
        return post
    except Exception as e:
        return error_response("Could not create post", 400)
    finally:
        conn.close()

# Get Single Post
@app.get("/posts/{postId}", response_model=Post)
def get_post(postId: str):
    conn = get_db()
    c = conn.cursor()
    post = c.execute("SELECT * FROM posts WHERE id=?", (postId,)).fetchone()
    if not post:
        conn.close()
        return error_response("Post not found", 404)
    likes = c.execute("SELECT COUNT(*) FROM likes WHERE postId=?", (postId,)).fetchone()[0]
    comments = c.execute("SELECT COUNT(*) FROM comments WHERE postId=?", (postId,)).fetchone()[0]
    result = Post(**dict(post), likes=likes, comments=comments)
    conn.close()
    return result

# Update Post
@app.patch("/posts/{postId}", response_model=Post)
def update_post(postId: str, data: PostUpdate):
    conn = get_db()
    c = conn.cursor()
    post = c.execute("SELECT * FROM posts WHERE id=?", (postId,)).fetchone()
    if not post:
        conn.close()
        return error_response("Post not found", 404)
    now = datetime.utcnow().isoformat()
    try:
        c.execute("UPDATE posts SET username=?, content=?, updatedAt=? WHERE id=?",
                  (data.username, data.content, now, postId))
        conn.commit()
        likes = c.execute("SELECT COUNT(*) FROM likes WHERE postId=?", (postId,)).fetchone()[0]
        comments = c.execute("SELECT COUNT(*) FROM comments WHERE postId=?", (postId,)).fetchone()[0]
        result = Post(id=postId, username=data.username, content=data.content, createdAt=post["createdAt"], updatedAt=now, likes=likes, comments=comments)
        return result
    except Exception as e:
        return error_response("Could not update post", 400)
    finally:
        conn.close()

# Delete Post
@app.delete("/posts/{postId}", status_code=204)
def delete_post(postId: str):
    conn = get_db()
    c = conn.cursor()
    post = c.execute("SELECT * FROM posts WHERE id=?", (postId,)).fetchone()
    if not post:
        conn.close()
        return error_response("Post not found", 404)
    c.execute("DELETE FROM posts WHERE id=?", (postId,))
    c.execute("DELETE FROM comments WHERE postId=?", (postId,))
    c.execute("DELETE FROM likes WHERE postId=?", (postId,))
    conn.commit()
    conn.close()
    return Response(status_code=204)

# List Comments for a Post
@app.get("/posts/{postId}/comments", response_model=List[Comment])
def list_comments(postId: str):
    conn = get_db()
    c = conn.cursor()
    comments = c.execute("SELECT * FROM comments WHERE postId=?", (postId,)).fetchall()
    result = [Comment(**dict(comment)) for comment in comments]
    conn.close()
    return result

# Create Comment
@app.post("/posts/{postId}/comments", response_model=Comment, status_code=201)
def create_comment(postId: str, data: CommentCreate):
    conn = get_db()
    c = conn.cursor()
    comment_id = os.urandom(8).hex()
    now = datetime.utcnow().isoformat()
    try:
        c.execute("INSERT INTO comments (id, postId, username, content, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?)",
                  (comment_id, postId, data.username, data.content, now, now))
        conn.commit()
        comment = Comment(id=comment_id, postId=postId, username=data.username, content=data.content, createdAt=now, updatedAt=now)
        return comment
    except Exception as e:
        return error_response("Could not create comment", 400)
    finally:
        conn.close()

# Get Specific Comment
@app.get("/posts/{postId}/comments/{commentId}", response_model=Comment)
def get_comment(postId: str, commentId: str):
    conn = get_db()
    c = conn.cursor()
    comment = c.execute("SELECT * FROM comments WHERE id=? AND postId=?", (commentId, postId)).fetchone()
    if not comment:
        conn.close()
        return error_response("Comment not found", 404)
    result = Comment(**dict(comment))
    conn.close()
    return result

# Update Comment
@app.patch("/posts/{postId}/comments/{commentId}", response_model=Comment)
def update_comment(postId: str, commentId: str, data: CommentUpdate):
    conn = get_db()
    c = conn.cursor()
    comment = c.execute("SELECT * FROM comments WHERE id=? AND postId=?", (commentId, postId)).fetchone()
    if not comment:
        conn.close()
        return error_response("Comment not found", 404)
    now = datetime.utcnow().isoformat()
    try:
        c.execute("UPDATE comments SET username=?, content=?, updatedAt=? WHERE id=? AND postId=?",
                  (data.username, data.content, now, commentId, postId))
        conn.commit()
        result = Comment(id=commentId, postId=postId, username=data.username, content=data.content, createdAt=comment["createdAt"], updatedAt=now)
        return result
    except Exception as e:
        return error_response("Could not update comment", 400)
    finally:
        conn.close()

# Delete Comment
@app.delete("/posts/{postId}/comments/{commentId}", status_code=204)
def delete_comment(postId: str, commentId: str):
    conn = get_db()
    c = conn.cursor()
    comment = c.execute("SELECT * FROM comments WHERE id=? AND postId=?", (commentId, postId)).fetchone()
    if not comment:
        conn.close()
        return error_response("Comment not found", 404)
    c.execute("DELETE FROM comments WHERE id=? AND postId=?", (commentId, postId))
    conn.commit()
    conn.close()
    return Response(status_code=204)

# Like a Post
@app.post("/posts/{postId}/likes", status_code=201)
def like_post(postId: str, data: LikeCreate):
    conn = get_db()
    c = conn.cursor()
    post = c.execute("SELECT * FROM posts WHERE id=?", (postId,)).fetchone()
    if not post:
        conn.close()
        return error_response("Post not found", 404)
    try:
        c.execute("INSERT INTO likes (postId, username) VALUES (?, ?)", (postId, data.username))
        conn.commit()
        return Response(status_code=201)
    except Exception as e:
        return error_response("Could not like post", 400)
    finally:
        conn.close()

# Unlike a Post
@app.delete("/posts/{postId}/likes", status_code=204)
def unlike_post(postId: str, data: LikeDelete):
    conn = get_db()
    c = conn.cursor()
    post = c.execute("SELECT * FROM posts WHERE id=?", (postId,)).fetchone()
    if not post:
        conn.close()
        return error_response("Post not found", 404)
    c.execute("DELETE FROM likes WHERE postId=? AND username=?", (postId, data.username))
    conn.commit()
    conn.close()
    return Response(status_code=204)

# --- Run the app on port 8000 ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
