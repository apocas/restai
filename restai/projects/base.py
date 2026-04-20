from restai.brain import Brain
from abc import ABC, abstractmethod
from restai.database import DBWrapper
from restai.models.models import ChatModel, QuestionModel, User
from fastapi import HTTPException
from restai.project import Project


class ProjectBase(ABC):
    def __init__(self, brain: Brain):
        self.brain: Brain = brain

    @abstractmethod
    async def chat(self, project: Project, chat_model: ChatModel, user: User, db: DBWrapper):
        raise HTTPException(status_code=400, detail="Chat mode not available for this project type.")

    @abstractmethod
    async def question(self, project: Project, question_model: QuestionModel, user: User, db: DBWrapper):
        raise HTTPException(status_code=400, detail="Question mode not available for this project type.")

    def check_input_guard(self, project: Project, question_text: str, user: User, db: DBWrapper, output: dict) -> bool:
        """Check input guard. Returns True if the request should be blocked (in block mode).

        Modifies output dict in-place (sets answer, guard flag).
        Logs guard events via background-compatible function.
        """
        if not project.props.guard:
            return False

        from restai.guard import Guard
        from restai.tools import log_guard_event

        guard = Guard(project.props.guard, self.brain, db)
        result = guard.verify(question_text, phase="input")
        if not result:
            return False

        guard_mode = project.props.options.guard_mode or "block"
        action = "block" if result.blocked else "pass"
        if result.blocked and guard_mode == "warn":
            action = "warn"

        log_guard_event(project, project.props.guard, user, "input", action, guard_mode, question_text, result.raw_response, db)

        if result.blocked and guard_mode == "block":
            output["answer"] = project.props.censorship or self.brain.defaultCensorship
            output["guard"] = True
            # Flag the inference log entry so the log viewer can show the
            # guard block distinctly from a normal answer.
            output["status"] = "guard_block"
            self.brain.post_processing_counting(output)
            return True
        elif result.blocked:
            output["guard"] = True
            output["status"] = "guard_block"

        return False

    def check_output_guard(self, project: Project, user: User, db: DBWrapper, output: dict) -> None:
        """Check the output guard against the answer in `output`. Mutates the
        output dict in place — sets `answer` to censorship and `guard=True` if
        a configured output guard blocks in `block` mode; just sets `guard=True`
        in `warn` mode. No-op when `guard_output` isn't configured or the
        answer is empty."""
        guard_name = project.props.options.guard_output if project.props.options else None
        if not guard_name or not output.get("answer"):
            return

        from restai.guard import Guard
        from restai.tools import log_guard_event

        out_guard = Guard(guard_name, self.brain, db)
        out_result = out_guard.verify(output["answer"], phase="output")
        if not out_result:
            return

        guard_mode = project.props.options.guard_mode or "block"
        action = "block" if out_result.blocked else "pass"
        if out_result.blocked and guard_mode == "warn":
            action = "warn"
        log_guard_event(
            project, guard_name, user, "output", action, guard_mode,
            output["answer"], out_result.raw_response, db,
        )

        if out_result.blocked and guard_mode == "block":
            output["answer"] = project.props.censorship or self.brain.defaultCensorship
            output["guard"] = True
        elif out_result.blocked:
            output["guard"] = True