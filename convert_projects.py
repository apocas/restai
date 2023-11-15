import json
import os

from app.database import Database, SessionLocal, dbc, get_db

for file in os.listdir("./projects/"):
    file_path = os.path.join("./projects/", file)
    if os.path.isfile(file_path):
        projectname, ext = os.path.splitext(file or '')
        if ext == ".json":
            file_path = os.path.join("./projects", f'{projectname}.json')

            with open(file_path, 'r') as f:
                model_json = json.load(f)
                db = SessionLocal()
                
                dbc.create_project(
                    db,
                    model_json["name"],
                    model_json["embeddings"],
                    model_json["llm"],
                    model_json["system"])
                
                db.close()
                