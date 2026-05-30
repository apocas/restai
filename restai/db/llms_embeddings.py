"""DBWrapper LLM / embedding / image-gen / speech-to-text methods (mixin).

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
)
from restai.models.models import (
    LLMModel, LLMUpdate, ProjectModelUpdate, User, UserUpdate, EmbeddingModel,
    EmbeddingUpdate, TeamModel, TeamModelUpdate, TeamModelCreate,
)
from restai.utils.crypto import decrypt_api_key, hash_api_key, verify_api_key_hash
from restai.db.passwords import hash_password, verify_password


class LLMEmbeddingMixin:
    __slots__ = ()

    def create_llm(
        self,
        name: str,
        class_name: str,
        options: str,
        privacy: str,
        description: str,
        context_window: int = 4096,
        input_cost: float = 0.0,
        output_cost: float = 0.0,
    ) -> LLMDatabase:
        from restai.utils.crypto import encrypt_sensitive_options, LLM_SENSITIVE_KEYS
        import json as _json
        try:
            opts_dict = _json.loads(options) if isinstance(options, str) else options
            opts_dict = encrypt_sensitive_options(opts_dict, LLM_SENSITIVE_KEYS)
            options = _json.dumps(opts_dict)
        except Exception as e:
            logging.warning("Failed to encrypt LLM options: %s", e)

        db_llm: LLMDatabase = LLMDatabase(
            name=name,
            class_name=class_name,
            options=options,
            privacy=privacy,
            description=description,
            context_window=context_window,
            input_cost=input_cost,
            output_cost=output_cost,
        )
        self.db.add(db_llm)
        self.db.commit()
        self.db.refresh(db_llm)
        return db_llm

    def create_embedding(
        self,
        name: str,
        class_name: str,
        options: str,
        privacy: str,
        description: str,
        dimension: int,
    ) -> EmbeddingDatabase:
        db_embedding: EmbeddingDatabase = EmbeddingDatabase(
            name=name,
            class_name=class_name,
            options=options,
            privacy=privacy,
            description=description,
            dimension=dimension,
        )
        self.db.add(db_embedding)
        self.db.commit()
        self.db.refresh(db_embedding)
        return db_embedding

    def get_llms(self) -> list[LLMDatabase]:
        llms: list[LLMDatabase] = self.db.query(LLMDatabase).all()
        return llms

    def get_embeddings(self) -> list[EmbeddingDatabase]:
        embeddings: list[EmbeddingDatabase] = self.db.query(EmbeddingDatabase).all()
        return embeddings

    def get_llm_by_name(self, name: str) -> Optional[LLMDatabase]:
        llm: Optional[LLMDatabase] = (
            self.db.query(LLMDatabase).filter(LLMDatabase.name == name).first()
        )
        return llm

    def get_llm_by_id(self, id: int) -> Optional[LLMDatabase]:
        return self.db.query(LLMDatabase).filter(LLMDatabase.id == id).first()

    def get_embedding_by_name(self, name: str) -> Optional[EmbeddingDatabase]:
        llm: Optional[EmbeddingDatabase] = (
            self.db.query(EmbeddingDatabase)
            .filter(EmbeddingDatabase.name == name)
            .first()
        )
        return llm

    def get_embedding_by_id(self, id: int) -> Optional[EmbeddingDatabase]:
        return self.db.query(EmbeddingDatabase).filter(EmbeddingDatabase.id == id).first()

    def update_llm(self, llm: LLMModel, llmUpdate: LLMUpdate) -> bool:
        if llmUpdate.class_name is not None and llm.class_name != llmUpdate.class_name:
            llm.class_name = llmUpdate.class_name

        if llmUpdate.options is not None and llm.options != llmUpdate.options:
            from restai.utils.crypto import encrypt_sensitive_options, LLM_SENSITIVE_KEYS
            import json as _json
            try:
                opts_dict = _json.loads(llmUpdate.options) if isinstance(llmUpdate.options, str) else llmUpdate.options
                # Preserve-on-mask: a resubmitted "********" means "keep the
                # stored secret". Covers EVERY sensitive key, not just api_key —
                # otherwise masking key/password/secret on GET would let an
                # unrelated edit overwrite the real value with the mask.
                existing = _json.loads(llm.options) if isinstance(llm.options, str) else (llm.options or {})
                for _k in LLM_SENSITIVE_KEYS:
                    if opts_dict.get(_k) == "********":
                        if _k in existing:
                            opts_dict[_k] = existing[_k]
                        else:
                            del opts_dict[_k]
                opts_dict = encrypt_sensitive_options(opts_dict, LLM_SENSITIVE_KEYS)
                llm.options = _json.dumps(opts_dict) if isinstance(llmUpdate.options, str) else opts_dict
            except Exception as e:
                logging.warning("Failed to encrypt LLM options on update: %s", e)
                llm.options = llmUpdate.options

        if llmUpdate.privacy is not None and llm.privacy != llmUpdate.privacy:
            llm.privacy = llmUpdate.privacy

        if (
            llmUpdate.description is not None
            and llm.description != llmUpdate.description
        ):
            llm.description = llmUpdate.description

        if llmUpdate.input_cost is not None and llm.input_cost != llmUpdate.input_cost:
            llm.input_cost = llmUpdate.input_cost

        if (
            llmUpdate.output_cost is not None
            and llm.output_cost != llmUpdate.output_cost
        ):
            llm.output_cost = llmUpdate.output_cost

        if (
            llmUpdate.context_window is not None
            and llm.context_window != llmUpdate.context_window
        ):
            llm.context_window = llmUpdate.context_window

        self.db.commit()
        return True

    def update_embedding(
        self, embedding: EmbeddingModel, embeddingUpdate: EmbeddingUpdate
    ) -> bool:
        if (
            embeddingUpdate.class_name is not None
            and embedding.class_name != embeddingUpdate.class_name
        ):
            embedding.class_name = embeddingUpdate.class_name

        if (
            embeddingUpdate.options is not None
            and embedding.options != embeddingUpdate.options
        ):
            import json as _json
            try:
                from restai.utils.crypto import LLM_SENSITIVE_KEYS
                new_opts = _json.loads(embeddingUpdate.options) if isinstance(embeddingUpdate.options, str) else (embeddingUpdate.options or {})
                existing = _json.loads(embedding.options) if isinstance(embedding.options, str) else (embedding.options or {})
                _changed = False
                for _k in LLM_SENSITIVE_KEYS:
                    if new_opts.get(_k) == "********":
                        if _k in existing:
                            new_opts[_k] = existing[_k]
                        else:
                            del new_opts[_k]
                        _changed = True
                if _changed:
                    embeddingUpdate.options = _json.dumps(new_opts)
            except Exception:
                pass
            embedding.options = embeddingUpdate.options

        if (
            embeddingUpdate.privacy is not None
            and embedding.privacy != embeddingUpdate.privacy
        ):
            embedding.privacy = embeddingUpdate.privacy

        if (
            embeddingUpdate.description is not None
            and embedding.description != embeddingUpdate.description
        ):
            embedding.description = embeddingUpdate.description

        if (
            embeddingUpdate.dimension is not None
            and embedding.dimension != embeddingUpdate.dimension
        ):
            embedding.dimension = embeddingUpdate.dimension

        self.db.commit()
        return True

    def delete_llm(self, llm: LLMDatabase) -> bool:
        self.db.delete(llm)
        self.db.commit()
        return True

    def delete_embedding(self, embedding: EmbeddingDatabase) -> bool:
        self.db.delete(embedding)
        self.db.commit()
        return True

    def get_image_generators(self) -> list[ImageGeneratorDatabase]:
        return self.db.query(ImageGeneratorDatabase).order_by(ImageGeneratorDatabase.name).all()

    def get_image_generator_by_id(self, gen_id: int) -> Optional[ImageGeneratorDatabase]:
        return self.db.query(ImageGeneratorDatabase).filter(ImageGeneratorDatabase.id == gen_id).first()

    def get_image_generator_by_name(self, name: str) -> Optional[ImageGeneratorDatabase]:
        return self.db.query(ImageGeneratorDatabase).filter(ImageGeneratorDatabase.name == name).first()

    def create_image_generator(
        self,
        name: str,
        class_name: str,
        options,
        privacy: str = "public",
        description: Optional[str] = None,
        enabled: bool = True,
    ) -> ImageGeneratorDatabase:
        from restai.utils.crypto import encrypt_sensitive_options, LLM_SENSITIVE_KEYS
        import json as _json

        try:
            opts_dict = _json.loads(options) if isinstance(options, str) else (options or {})
            opts_dict = encrypt_sensitive_options(opts_dict, LLM_SENSITIVE_KEYS)
            options_str = _json.dumps(opts_dict)
        except Exception as e:
            logging.warning("Failed to encrypt image generator options: %s", e)
            options_str = options if isinstance(options, str) else _json.dumps(options or {})

        now = datetime.now(timezone.utc)
        row = ImageGeneratorDatabase(
            name=name,
            class_name=class_name,
            options=options_str,
            privacy=privacy,
            description=description,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def edit_image_generator(self, gen: ImageGeneratorDatabase, update) -> bool:
        """Patch an image generator. `update` is an ImageGeneratorModelUpdate.
        api_key in `options` is preserved when the submitted value is the
        masked sentinel `"********"` (matches the LLM edit pattern)."""
        from restai.utils.crypto import encrypt_sensitive_options, LLM_SENSITIVE_KEYS
        import json as _json

        changed = False
        if update.class_name is not None and gen.class_name != update.class_name:
            gen.class_name = update.class_name
            changed = True

        if update.options is not None:
            try:
                new_opts = _json.loads(update.options) if isinstance(update.options, str) else (update.options or {})
                existing = _json.loads(gen.options) if gen.options else {}
                # them so the comparison is plaintext-vs-plaintext.
                from restai.utils.crypto import decrypt_sensitive_options
                existing_plain = decrypt_sensitive_options(dict(existing), LLM_SENSITIVE_KEYS)
                for k in LLM_SENSITIVE_KEYS:
                    val = new_opts.get(k)
                    if isinstance(val, str) and val == "********":
                        if k in existing_plain:
                            new_opts[k] = existing_plain[k]
                        else:
                            new_opts.pop(k, None)
                new_opts_enc = encrypt_sensitive_options(new_opts, LLM_SENSITIVE_KEYS)
                gen.options = _json.dumps(new_opts_enc)
                changed = True
            except Exception as e:
                logging.warning("Failed to update image generator options: %s", e)

        if update.privacy is not None and gen.privacy != update.privacy:
            gen.privacy = update.privacy
            changed = True

        if update.description is not None and gen.description != update.description:
            gen.description = update.description
            changed = True

        if update.enabled is not None and gen.enabled != update.enabled:
            gen.enabled = update.enabled
            changed = True

        if changed:
            gen.updated_at = datetime.now(timezone.utc)
            self.db.commit()
        return changed

    def delete_image_generator(self, gen: ImageGeneratorDatabase) -> bool:
        # Also drop any team grants pointing at this name so we don't leave
        # dangling rows in the legacy string-keyed teams_image_generators.
        try:
            self.db.query(TeamImageGeneratorDatabase).filter(
                TeamImageGeneratorDatabase.generator_name == gen.name
            ).delete(synchronize_session=False)
        except Exception:
            pass
        self.db.delete(gen)
        self.db.commit()
        return True

    def get_speech_to_text(self) -> list[SpeechToTextDatabase]:
        return self.db.query(SpeechToTextDatabase).order_by(SpeechToTextDatabase.name).all()

    def get_speech_to_text_by_id(self, model_id: int) -> Optional[SpeechToTextDatabase]:
        return self.db.query(SpeechToTextDatabase).filter(SpeechToTextDatabase.id == model_id).first()

    def get_speech_to_text_by_name(self, name: str) -> Optional[SpeechToTextDatabase]:
        return self.db.query(SpeechToTextDatabase).filter(SpeechToTextDatabase.name == name).first()

    def create_speech_to_text(
        self,
        name: str,
        class_name: str,
        options,
        privacy: str = "public",
        description: Optional[str] = None,
        enabled: bool = True,
    ) -> SpeechToTextDatabase:
        from restai.utils.crypto import encrypt_sensitive_options, LLM_SENSITIVE_KEYS
        import json as _json

        try:
            opts_dict = _json.loads(options) if isinstance(options, str) else (options or {})
            opts_dict = encrypt_sensitive_options(opts_dict, LLM_SENSITIVE_KEYS)
            options_str = _json.dumps(opts_dict)
        except Exception as e:
            logging.warning("Failed to encrypt speech-to-text options: %s", e)
            options_str = options if isinstance(options, str) else _json.dumps(options or {})

        now = datetime.now(timezone.utc)
        row = SpeechToTextDatabase(
            name=name,
            class_name=class_name,
            options=options_str,
            privacy=privacy,
            description=description,
            enabled=enabled,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def edit_speech_to_text(self, model: SpeechToTextDatabase, update) -> bool:
        """Patch a speech-to-text row. `"********"` in `options.api_key`
        preserves the existing value (matches the LLM/image-gen pattern)."""
        from restai.utils.crypto import (
            decrypt_sensitive_options,
            encrypt_sensitive_options,
            LLM_SENSITIVE_KEYS,
        )
        import json as _json

        changed = False
        if update.class_name is not None and model.class_name != update.class_name:
            model.class_name = update.class_name
            changed = True

        if update.options is not None:
            try:
                new_opts = _json.loads(update.options) if isinstance(update.options, str) else (update.options or {})
                existing = _json.loads(model.options) if model.options else {}
                existing_plain = decrypt_sensitive_options(dict(existing), LLM_SENSITIVE_KEYS)
                for k in LLM_SENSITIVE_KEYS:
                    val = new_opts.get(k)
                    if isinstance(val, str) and val == "********":
                        if k in existing_plain:
                            new_opts[k] = existing_plain[k]
                        else:
                            new_opts.pop(k, None)
                new_opts_enc = encrypt_sensitive_options(new_opts, LLM_SENSITIVE_KEYS)
                model.options = _json.dumps(new_opts_enc)
                changed = True
            except Exception as e:
                logging.warning("Failed to update speech-to-text options: %s", e)

        if update.privacy is not None and model.privacy != update.privacy:
            model.privacy = update.privacy
            changed = True
        if update.description is not None and model.description != update.description:
            model.description = update.description
            changed = True
        if update.enabled is not None and model.enabled != update.enabled:
            model.enabled = update.enabled
            changed = True

        if changed:
            model.updated_at = datetime.now(timezone.utc)
            self.db.commit()
        return changed

    def delete_speech_to_text(self, model: SpeechToTextDatabase) -> bool:
        try:
            self.db.query(TeamAudioGeneratorDatabase).filter(
                TeamAudioGeneratorDatabase.generator_name == model.name
            ).delete(synchronize_session=False)
        except Exception:
            pass
        self.db.delete(model)
        self.db.commit()
        return True
