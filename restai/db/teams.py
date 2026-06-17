"""DBWrapper team membership + resource-attach methods (mixin).

Split out of the former monolithic restai/database.py. Each method still uses
`self.db` (the shared Session); the concrete `DBWrapper` in restai/database.py
composes these mixins, so the public API is unchanged.
"""

import json
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import func, or_

from restai.models.databasemodels import (
    ApiKeyDatabase, LLMDatabase, EmbeddingDatabase, OutputDatabase, ProjectDatabase,
    ProjectToolDatabase, ProjectRoutineDatabase, CronLogDatabase, SettingDatabase,
    UserDatabase, TeamDatabase, TeamImageGeneratorDatabase, TeamAudioGeneratorDatabase,
    WidgetDatabase, ImageGeneratorDatabase, SpeechToTextDatabase, ProjectSecretDatabase,
    TeamUserBudgetDatabase, TeamBalanceTransactionDatabase,
)
from restai.models.models import (
    LLMModel, LLMUpdate, ProjectModelUpdate, User, UserUpdate, EmbeddingModel,
    EmbeddingUpdate, TeamModel, TeamModelUpdate, TeamModelCreate,
)
from restai.utils.crypto import decrypt_api_key, hash_api_key, verify_api_key_hash
from restai.db.passwords import hash_password, verify_password


class TeamMixin:
    __slots__ = ()

    def create_team(self, team_create: TeamModelCreate) -> TeamDatabase:
        db_team: TeamDatabase = TeamDatabase(
            name=team_create.name,
            description=team_create.description,
            creator_id=team_create.creator_id,
            budget=team_create.budget,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(db_team)
        self.db.commit()
        self.db.refresh(db_team)
        return db_team

    def get_team_by_id(self, team_id: int) -> Optional[TeamDatabase]:
        team: Optional[TeamDatabase] = (
            self.db.query(TeamDatabase).filter(TeamDatabase.id == team_id).first()
        )
        return team

    def get_team_by_name(self, name: str) -> Optional[TeamDatabase]:
        team: Optional[TeamDatabase] = (
            self.db.query(TeamDatabase).filter(TeamDatabase.name == name).first()
        )
        return team

    def get_teams(self) -> List[TeamDatabase]:
        teams: List[TeamDatabase] = self.db.query(TeamDatabase).all()
        return teams

    def update_team(self, team: TeamDatabase, team_update: TeamModelUpdate) -> bool:
        changed = False

        if team_update.name is not None and team.name != team_update.name:
            team.name = team_update.name
            changed = True

        if team_update.description is not None and team.description != team_update.description:
            team.description = team_update.description
            changed = True

        if team_update.budget is not None and team.budget != team_update.budget:
            team.budget = team_update.budget
            changed = True

        if team_update.branding is not None:
            import json
            team.branding = json.dumps(team_update.branding.model_dump())
            changed = True

        if team_update.options is not None:
            import json as _json
            from restai.utils.crypto import encrypt_sensitive_options, TEAM_SENSITIVE_KEYS
            incoming = team_update.options.model_dump(exclude_none=True)
            # Preserve existing secret when caller submits the masked placeholder.
            existing = _json.loads(team.options) if team.options else {}
            for k in TEAM_SENSITIVE_KEYS:
                v = incoming.get(k)
                if v is None or v == "" or (isinstance(v, str) and v.startswith("****")):
                    if k in existing:
                        incoming[k] = existing[k]
                    else:
                        incoming.pop(k, None)
            encrypted = encrypt_sensitive_options(incoming, TEAM_SENSITIVE_KEYS)
            team.options = _json.dumps(encrypted)
            changed = True

        if changed:
            team.updated_at = datetime.now(timezone.utc)
            self.db.commit()
        return changed

    def delete_team(self, team: TeamDatabase) -> bool:
        self.db.delete(team)
        self.db.commit()
        return True

    def add_user_to_team(self, team: TeamDatabase, user: UserDatabase) -> bool:
        if user not in team.users:
            team.users.append(user)
            self.db.commit()
        return True

    def remove_user_from_team(self, team: TeamDatabase, user: UserDatabase) -> bool:
        if user in team.users:
            team.users.remove(user)
            self.db.commit()
        return True

    def add_admin_to_team(self, team: TeamDatabase, user: UserDatabase) -> bool:
        if user not in team.admins:
            team.admins.append(user)
            self.db.commit()
        return True

    def remove_admin_from_team(self, team: TeamDatabase, user: UserDatabase) -> bool:
        if user in team.admins:
            team.admins.remove(user)
            self.db.commit()
        return True

    def add_project_to_team(self, team: TeamDatabase, project: ProjectDatabase) -> bool:
        if project not in team.projects:
            team.projects.append(project)
            self.db.commit()
        return True

    def remove_project_from_team(self, team: TeamDatabase, project: ProjectDatabase) -> bool:
        if project in team.projects:
            team.projects.remove(project)
            self.db.commit()
        return True

    def add_llm_to_team(self, team: TeamDatabase, llm: LLMDatabase) -> bool:
        if llm not in team.llms:
            team.llms.append(llm)
            self.db.commit()
        return True

    def remove_llm_from_team(self, team: TeamDatabase, llm: LLMDatabase) -> bool:
        if llm in team.llms:
            team.llms.remove(llm)
            self.db.commit()
        return True

    def add_embedding_to_team(self, team: TeamDatabase, embedding: EmbeddingDatabase) -> bool:
        if embedding not in team.embeddings:
            team.embeddings.append(embedding)
            self.db.commit()
        return True

    def remove_embedding_from_team(self, team: TeamDatabase, embedding: EmbeddingDatabase) -> bool:
        if embedding in team.embeddings:
            team.embeddings.remove(embedding)
            self.db.commit()
        return True

    def get_teams_for_user(self, user_id: int) -> List[TeamDatabase]:
        user = self.get_user_by_id(user_id)
        if user is None:
            return []
        return list(set(user.teams + user.admin_teams))

    @staticmethod
    def _month_start() -> datetime:
        now = datetime.now(timezone.utc)
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def spend_for(self, *, team_id=None, user_id=None, project_id=None,
                  api_key_id=None, since: Optional[datetime] = None) -> float:
        """Unified cost-budget spend: SUM(input_cost + output_cost) over OutputDatabase
        filtered by the supplied scope(s), ANDed together, since `since` (default = first
        of this month UTC). Scopes:
          - team_id   → or_(project in team's projects, OutputDatabase.team_id == team_id)
          - user_id   → OutputDatabase.user_id == user_id   (AND with team_id = user-in-team)
          - project_id→ OutputDatabase.project_id == project_id
          - api_key_id→ OutputDatabase.api_key_id == api_key_id
        At least one scope is required (guards against an unfiltered full-table sum)."""
        if team_id is None and user_id is None and project_id is None and api_key_id is None:
            raise ValueError("spend_for requires at least one scope")
        if since is None:
            since = self._month_start()
        filters = [OutputDatabase.date >= since]
        if team_id is not None:
            filters.append(
                or_(
                    OutputDatabase.project_id.in_(
                        self.db.query(ProjectDatabase.id).filter(ProjectDatabase.team_id == team_id)
                    ),
                    OutputDatabase.team_id == team_id,
                )
            )
        if user_id is not None:
            filters.append(OutputDatabase.user_id == user_id)
        if project_id is not None:
            filters.append(OutputDatabase.project_id == project_id)
        if api_key_id is not None:
            filters.append(OutputDatabase.api_key_id == api_key_id)
        result = self.db.query(
            func.coalesce(func.sum(OutputDatabase.input_cost + OutputDatabase.output_cost), 0.0)
        ).filter(*filters).scalar()
        return float(result or 0.0)

    def get_team_spending(self, team_id: int) -> float:
        return self.spend_for(team_id=team_id)

    def get_team_user_spending(self, team_id: int, user_id: int) -> float:
        return self.spend_for(team_id=team_id, user_id=user_id)

    def get_team_user_spending_map(self, team_id: int) -> dict:
        """{user_id: month-to-date cost} for every user with spend in the team scope.
        One grouped query — avoids N+1 over the member list."""
        since = self._month_start()
        rows = (
            self.db.query(
                OutputDatabase.user_id,
                func.coalesce(func.sum(OutputDatabase.input_cost + OutputDatabase.output_cost), 0.0),
            )
            .filter(
                or_(
                    OutputDatabase.project_id.in_(
                        self.db.query(ProjectDatabase.id).filter(ProjectDatabase.team_id == team_id)
                    ),
                    OutputDatabase.team_id == team_id,
                ),
                OutputDatabase.date >= since,
            )
            .group_by(OutputDatabase.user_id)
            .all()
        )
        return {uid: float(cost or 0.0) for uid, cost in rows if uid is not None}

    # ---- per-(user, team) budget caps ------------------------------------
    def get_team_user_budget(self, team_id: int, user_id: int) -> Optional[float]:
        """The member's monthly cost cap, or None when uncapped (no row / -1)."""
        row = (
            self.db.query(TeamUserBudgetDatabase)
            .filter(
                TeamUserBudgetDatabase.team_id == team_id,
                TeamUserBudgetDatabase.user_id == user_id,
            )
            .first()
        )
        if row is None or row.budget is None or row.budget < 0:
            return None
        return float(row.budget)

    def get_team_user_budgets_map(self, team_id: int) -> dict:
        """{user_id: cap} for members with an explicit cap (>= 0) in this team."""
        rows = (
            self.db.query(TeamUserBudgetDatabase)
            .filter(TeamUserBudgetDatabase.team_id == team_id)
            .all()
        )
        return {r.user_id: float(r.budget) for r in rows if r.budget is not None and r.budget >= 0}

    def set_team_user_budget(self, team_id: int, user_id: int, budget) -> None:
        """Upsert a member's cap. budget None or < 0 clears it (delete row)."""
        row = (
            self.db.query(TeamUserBudgetDatabase)
            .filter(
                TeamUserBudgetDatabase.team_id == team_id,
                TeamUserBudgetDatabase.user_id == user_id,
            )
            .first()
        )
        if budget is None or budget < 0:
            if row is not None:
                self.db.delete(row)
                self.db.commit()
            return
        if row is None:
            row = TeamUserBudgetDatabase(team_id=team_id, user_id=user_id, budget=float(budget))
            self.db.add(row)
        else:
            row.budget = float(budget)
        self.db.commit()

    def add_balance_transaction(self, team_id: int, amount: float, balance_after: float,
                                kind: str, description: Optional[str] = None,
                                actor_user_id: Optional[int] = None) -> TeamBalanceTransactionDatabase:
        """Record one prepaid-wallet movement. Does NOT commit, so it joins the
        caller's atomic commit (the same one that mutates teams.balance)."""
        row = TeamBalanceTransactionDatabase(
            team_id=team_id,
            amount=float(amount),
            balance_after=float(balance_after),
            kind=kind,
            description=description,
            actor_user_id=actor_user_id,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(row)
        return row

    def list_balance_transactions(self, team_id: int, start: int, end: int):
        """Paginated wallet ledger for a team (newest first). Returns
        (rows, total) where each row is (TeamBalanceTransactionDatabase, actor_username)."""
        base_query = (
            self.db.query(
                TeamBalanceTransactionDatabase,
                UserDatabase.username.label("actor_username"),
            )
            .outerjoin(UserDatabase, TeamBalanceTransactionDatabase.actor_user_id == UserDatabase.id)
            .filter(TeamBalanceTransactionDatabase.team_id == team_id)
        )
        total = base_query.count()
        rows = (
            base_query
            .order_by(TeamBalanceTransactionDatabase.created_at.desc(),
                      TeamBalanceTransactionDatabase.id.desc())
            .offset(start)
            .limit(end - start)
            .all()
        )
        return rows, total

    def update_team_members(
        self,
        team: TeamDatabase,
        team_update: TeamModelUpdate,
        caller=None,
    ) -> bool:
        """Rebuild the team's M2M sets from name lists in `team_update`.

        `caller` is the `User` initiating the change. When supplied AND
        not a platform admin, the caller is gated through the same
        per-resource attach checks the dedicated endpoints use — this
        plugs the parallel privilege-escalation hole where a team admin
        could pass a name list referring to another team's resources.

        Validation happens before mutation: if any check fails the team
        is left untouched (no half-rebuilt allow-list). Missing-by-name
        rows are silently skipped — same legacy behavior as before.

        `caller=None` keeps the method backward-compatible for callers
        that have already authorized the action (e.g. internal tasks),
        but the user-facing router path always passes `caller`.
        """
        from restai.auth import (
            check_user_can_attach_project,
            check_user_can_attach_llm,
            check_user_can_attach_embedding,
        )

        # ── Phase 1: resolve names → DB rows for every section the
        # update touches. Skips rows that don't exist (legacy behavior).
        resolved_users = None
        resolved_admins = None
        resolved_projects = None
        resolved_llms = None
        resolved_embeddings = None

        if team_update.users is not None:
            resolved_users = [
                u for u in (self.get_user_by_username(n) for n in team_update.users)
                if u is not None
            ]
        if team_update.admins is not None:
            resolved_admins = [
                u for u in (self.get_user_by_username(n) for n in team_update.admins)
                if u is not None
            ]
        if team_update.projects is not None:
            resolved_projects = [
                p for p in (self.get_project_by_name(n) for n in team_update.projects)
                if p is not None
            ]
        if team_update.llms is not None:
            resolved_llms = [
                l for l in (self.get_llm_by_name(n) for n in team_update.llms)
                if l is not None
            ]
        if team_update.embeddings is not None:
            resolved_embeddings = [
                e for e in (self.get_embedding_by_name(n) for n in team_update.embeddings)
                if e is not None
            ]

        # ── Phase 2: validate every newly-attached resource through the
        # caller's attach permissions. Raises 403 on first denial, leaves
        # the team untouched. Platform admins (`caller.is_admin`) and
        # internal callers (`caller is None`) skip the gate.
        if caller is not None and not getattr(caller, "is_admin", False):
            existing_project_ids = {p.id for p in (team.projects or [])}
            for project in resolved_projects or []:
                if project.id in existing_project_ids:
                    continue  # already attached → not a new grant
                check_user_can_attach_project(caller, project)

            existing_llm_ids = {l.id for l in (team.llms or [])}
            for llm in resolved_llms or []:
                if llm.id in existing_llm_ids:
                    continue
                check_user_can_attach_llm(caller, llm)

            existing_embedding_ids = {e.id for e in (team.embeddings or [])}
            for emb in resolved_embeddings or []:
                if emb.id in existing_embedding_ids:
                    continue
                check_user_can_attach_embedding(caller, emb)

        # ── Phase 3: mutate. Order matches the legacy implementation.
        changed = False

        if resolved_users is not None:
            team.users = list(resolved_users)
            changed = True

        if resolved_admins is not None:
            team.admins = list(resolved_admins)
            changed = True

        if resolved_projects is not None:
            team.projects = list(resolved_projects)
            changed = True

        if resolved_llms is not None:
            team.llms = list(resolved_llms)
            changed = True

        if resolved_embeddings is not None:
            team.embeddings = list(resolved_embeddings)
            changed = True

        if team_update.image_generators is not None:
            team.image_generators = []
            self.db.flush()
            for gen_name in team_update.image_generators:
                team.image_generators.append(
                    TeamImageGeneratorDatabase(team_id=team.id, generator_name=gen_name)
                )
            changed = True

        if team_update.audio_generators is not None:
            team.audio_generators = []
            self.db.flush()
            for gen_name in team_update.audio_generators:
                team.audio_generators.append(
                    TeamAudioGeneratorDatabase(team_id=team.id, generator_name=gen_name)
                )
            changed = True

        if changed:
            team.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            
        return changed

    def add_image_generator_to_team(self, team: TeamDatabase, generator_name: str) -> bool:
        existing = self.db.query(TeamImageGeneratorDatabase).filter(
            TeamImageGeneratorDatabase.team_id == team.id,
            TeamImageGeneratorDatabase.generator_name == generator_name
        ).first()
        if existing is None:
            team.image_generators.append(
                TeamImageGeneratorDatabase(team_id=team.id, generator_name=generator_name)
            )
            self.db.commit()
        return True

    def remove_image_generator_from_team(self, team: TeamDatabase, generator_name: str) -> bool:
        item = self.db.query(TeamImageGeneratorDatabase).filter(
            TeamImageGeneratorDatabase.team_id == team.id,
            TeamImageGeneratorDatabase.generator_name == generator_name
        ).first()
        if item is not None:
            self.db.delete(item)
            self.db.commit()
        return True

    def add_audio_generator_to_team(self, team: TeamDatabase, generator_name: str) -> bool:
        existing = self.db.query(TeamAudioGeneratorDatabase).filter(
            TeamAudioGeneratorDatabase.team_id == team.id,
            TeamAudioGeneratorDatabase.generator_name == generator_name
        ).first()
        if existing is None:
            team.audio_generators.append(
                TeamAudioGeneratorDatabase(team_id=team.id, generator_name=generator_name)
            )
            self.db.commit()
        return True

    def remove_audio_generator_from_team(self, team: TeamDatabase, generator_name: str) -> bool:
        item = self.db.query(TeamAudioGeneratorDatabase).filter(
            TeamAudioGeneratorDatabase.team_id == team.id,
            TeamAudioGeneratorDatabase.generator_name == generator_name
        ).first()
        if item is not None:
            self.db.delete(item)
            self.db.commit()
        return True
