from app.models import QuestionModel

class Guard:
    def __init__(self, projectName, brain, db):        
        self.brain = brain
        self.projectName = projectName
        self.db = db

    def verify(self, prompt):
        output = self.brain.inference(self.projectName, QuestionModel(question="Analyze the following text:\n\"" + prompt + "\""), self.db)
      
        for response in output:
            answer = response["answer"].strip()
            try:
                if answer == "BAD":
                    return True
                elif answer == "GOOD":
                    return False
                else:
                    return True
            except Exception as e:
                raise e
              
        raise Exception("Invalid response. Does the guardian project's model support prompt guard?")
