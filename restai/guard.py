import logging
from dataclasses import dataclass
from typing import Optional

from llama_index.core.base.llms.types import ChatMessage, MessageRole

from restai.brain import Brain
from restai.database import DBWrapper
from restai.llm import LLM
from restai.project import Project

logger = logging.getLogger(__name__)

BLOCK_KEYWORDS = {"BAD", "NOK", "NO", "FALSE", "DENY", "BLOCK", "REJECT", "UNSAFE"}
ALLOW_KEYWORDS = {"GOOD", "OK", "YES", "TRUE", "ALLOW", "PASS", "SAFE", "APPROVE"}


@dataclass
class GuardResult:
    blocked: bool
    raw_response: str


class Guard:
    def __init__(self, projectName: str, brain: Brain, db: DBWrapper):
        self.brain: Brain = brain
        self.db: DBWrapper = db
        self.guard_project_name = projectName
        self.project: Optional[Project] = None

        try:
            project_db = db.get_project_by_name(projectName)
            if project_db:
                self.project = brain.find_project(project_db.id, db)
        except Exception as e:
            logger.warning("Failed to load guard project '%s': %s", projectName, e)

    def verify(self, text: str, phase: str = "input") -> Optional[GuardResult]:
        if self.project is None:
            logger.warning("Guard project '%s' not found, skipping", self.guard_project_name)
            return None

        model: Optional[LLM] = self.brain.get_llm(self.project.props.llm, self.db)
        if model is None:
            logger.warning("Guard project '%s' has no valid LLM, skipping", self.guard_project_name)
            return None

        sysTemplate: Optional[str] = self.project.props.system
        if sysTemplate:
            model.llm.system_prompt = sysTemplate

        if phase == "output":
            prompt = f'Analyze the following response:\n"{text}"'
        else:
            prompt = f'Analyze the following text:\n"{text}"'

        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=sysTemplate or ""),
            ChatMessage(role=MessageRole.USER, content=prompt),
        ]

        try:
            resp = model.llm.chat(messages)
            answer: str = resp.message.content.strip()
        except Exception as e:
            logger.exception("Guard LLM call failed: %s", e)
            return GuardResult(blocked=True, raw_response=f"Error: {e}")

        blocked = self._parse_response(answer)
        return GuardResult(blocked=blocked, raw_response=answer)

    @staticmethod
    def _parse_response(answer: str) -> bool:
        """Parse guard response. Returns True if blocked."""
        first_line = answer.strip().split("\n")[0].strip().upper()
        for kw in BLOCK_KEYWORDS:
            if kw in first_line:
                return True
        for kw in ALLOW_KEYWORDS:
            if kw in first_line:
                return False
        # Default: block (fail-safe)
        return True
