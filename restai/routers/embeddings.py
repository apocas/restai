from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse, Response
from typing import Optional
import base64
import io
import os
from restai.auth import get_current_user
from restai.database import get_db
from restai.models.databasemodels import User, Embeddings
from restai.project import get_project
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/projects/{project_name}/embeddings")
def get_embeddings(project_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = get_project(project_name, current_user, db)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    embeddings = db.query(Embeddings).filter(Embeddings.project_name == project_name).all()
    return embeddings


@router.get("/projects/{project_name}/embeddings/source/{source}")
def get_embedding_source(project_name: str, source: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = get_project(project_name, current_user, db)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Decode the base64 encoded source
    try:
        decoded_source = base64.b64decode(source).decode('utf-8')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid source encoding: {str(e)}")
    
    # Get the embedding
    embedding = db.query(Embeddings).filter(
        Embeddings.project_name == project_name,
        Embeddings.source == decoded_source
    ).first()
    
    if embedding is None:
        raise HTTPException(status_code=404, detail="Embedding not found")
    
    # Read the file content
    if embedding.source_type == "file" and embedding.source_path:
        try:
            with open(embedding.source_path, 'rb') as f:
                content = f.read()
            
            # Try to decode as UTF-8 for text files, otherwise return binary
            try:
                text_content = content.decode('utf-8')
                return {"source": decoded_source, "content": text_content, "type": "text"}
            except UnicodeDecodeError:
                # For binary files (PDFs, images, etc.), return as base64
                return {"source": decoded_source, "content": base64.b64encode(content).decode('ascii'), "type": "binary"}
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Source file not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")
    else:
        # For text content stored in DB
        return {"source": decoded_source, "content": embedding.content or "", "type": "text"}


@router.delete("/projects/{project_name}/embeddings/source/{source}")
def delete_embedding_source(project_name: str, source: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = get_project(project_name, current_user, db)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Decode the base64 encoded source
    try:
        decoded_source = base64.b64decode(source).decode('utf-8')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid source encoding: {str(e)}")
    
    # Delete embeddings with this source
    embeddings = db.query(Embeddings).filter(
        Embeddings.project_name == project_name,
        Embeddings.source == decoded_source
    ).all()
    
    if not embeddings:
        raise HTTPException(status_code=404, detail="Embedding not found")
    
    # Delete associated files if they exist
    for embedding in embeddings:
        if embedding.source_type == "file" and embedding.source_path:
            try:
                if os.path.exists(embedding.source_path):
                    os.remove(embedding.source_path)
            except Exception as e:
                print(f"Error deleting file: {str(e)}")
        
        db.delete(embedding)
    
    db.commit()
    
    return {"message": "Embeddings deleted successfully"}


@router.post("/projects/{project_name}/embeddings")
async def upload_embedding(
    project_name: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    project = get_project(project_name, current_user, db)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Save the uploaded file
    file_content = await file.read()
    
    # Process the file based on project type
    try:
        project.ingest_file(file.filename, file_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
    
    return {"message": "File uploaded and processed successfully", "filename": file.filename}
