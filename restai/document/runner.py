from pathlib import Path
from torch.multiprocessing import Process
from ilock import ILock
from llama_index.readers.docling import DoclingReader
import torch

def worker(file_path: str, sharedmem):
    """Worker process for loading documents using docling"""
    try:
        reader = DoclingReader()
        documents = reader.load_data(file_path=Path(file_path))
        
        # Convert documents to a format that can be shared via sharedmem
        docs_data = []
        for doc in documents:
            docs_data.append({
                'text': doc.text,
                'metadata': doc.metadata
            })
        
        sharedmem['documents'] = docs_data
        sharedmem['error'] = None
        
    except Exception as e:
        sharedmem['error'] = str(e)
        sharedmem['documents'] = None
    finally:
        del reader
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

def load_documents(manager, file_path: str):
    """Load documents using docling in a separate process"""
    sharedmem = manager.dict()
    
    p = Process(target=worker, args=(file_path, sharedmem))
    p.start()
    p.join()
    p.kill()

    if sharedmem.get('error'):
        raise Exception(sharedmem['error'])

    if not sharedmem.get('documents'):
        raise Exception("No documents were loaded")

    # Convert back to Document objects
    from llama_index.core.schema import Document
    documents = []
    for doc_data in sharedmem['documents']:
        documents.append(Document(
            text=doc_data['text'],
            metadata=doc_data['metadata']
        ))

    return documents 