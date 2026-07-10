from restai.brain import Brain
from abc import ABC, abstractmethod
from restai.database import DBWrapper
from restai.models.models import ChatModel, User
from fastapi import HTTPException
from restai.project import Project


def _account_guard(guard, user: User, text: str, result, db: DBWrapper) -> None:
    """Log the guard LLM call as an accounted OutputDatabase row against the guard
    project (its own team/LLM pricing). Best-effort — never breaks the turn."""
    if getattr(guard, "project", None) is None:
        return
    try:
        from restai.tools import log_inference
        log_inference(guard.project, user, {
            "question": text,
            "answer": result.raw_response,
            "tokens": {"input": result.input_tokens, "output": result.output_tokens},
            "status": "guard",
        }, db)
    except Exception:
        pass


class ProjectBase(ABC):
    def __init__(self, brain: Brain):
        self.brain: Brain = brain

    @abstractmethod
    async def chat(self, project: Project, chat_model: ChatModel, user: User, db: DBWrapper):
        raise HTTPException(status_code=400, detail="Chat mode not available for this project type.")

    def check_input_guard(self, project: Project, question_text: str, user: User, db: DBWrapper, output: dict) -> bool:
        """Returns True if the request should be blocked; mutates output dict in place."""
        if not project.props.guard:
            return False

        from restai.limits.guard import Guard
        from restai.tools import log_guard_event

        guard = Guard(project.props.guard, self.brain, db)
        result = guard.verify(question_text, phase="input")
        if not result:
            return False

        _account_guard(guard, user, question_text, result, db)

        guard_mode = project.props.options.guard_mode or "block"
        action = "block" if result.blocked else "pass"
        if result.blocked and guard_mode == "warn":
            action = "warn"

        guard_label = guard.project.props.name if guard.project else str(project.props.guard)
        log_guard_event(project, guard_label, user, "input", action, guard_mode, question_text, result.raw_response, db)

        if result.blocked and guard_mode == "block":
            output["answer"] = project.props.censorship or self.brain.defaultCensorship
            output["guard"] = True
            output["status"] = "guard_block"
            self.brain.post_processing_counting(output)
            return True
        elif result.blocked:
            output["guard"] = True
            output["status"] = "guard_block"

        return False

    def check_output_guard(self, project: Project, user: User, db: DBWrapper, output: dict) -> None:
        """Run output guard against output['answer']; mutates output in place."""
        guard_name = project.props.options.guard_output if project.props.options else None
        if not guard_name or not output.get("answer"):
            return

        from restai.limits.guard import Guard
        from restai.tools import log_guard_event

        out_guard = Guard(guard_name, self.brain, db)
        out_result = out_guard.verify(output["answer"], phase="output")
        if not out_result:
            return

        _account_guard(out_guard, user, output["answer"], out_result, db)

        guard_mode = project.props.options.guard_mode or "block"
        action = "block" if out_result.blocked else "pass"
        if out_result.blocked and guard_mode == "warn":
            action = "warn"
        guard_label = out_guard.project.props.name if out_guard.project else str(guard_name)
        log_guard_event(
            project, guard_label, user, "output", action, guard_mode,
            output["answer"], out_result.raw_response, db,
        )

        if out_result.blocked and guard_mode == "block":
            output["answer"] = project.props.censorship or self.brain.defaultCensorship
            output["guard"] = True
        elif out_result.blocked:
            output["guard"] = True