"""DBWrapper platform-settings methods (mixin).

Split out of the former monolithic restai/database.py. Each method still uses
`self.db` (the shared Session); the concrete `DBWrapper` in restai/database.py
composes these mixins, so the public API is unchanged.
"""

from typing import Optional


from restai.models.databasemodels import (
    SettingDatabase,
)


class SettingMixin:
    __slots__ = ()

    def get_settings(self) -> list[SettingDatabase]:
        from restai.utils.crypto import SETTINGS_ENCRYPTED_KEYS, decrypt_field
        rows = self.db.query(SettingDatabase).all()
        for r in rows:
            if r.key in SETTINGS_ENCRYPTED_KEYS and r.value:
                self.db.expunge(r)
                r.value = decrypt_field(r.value)
        return rows

    def get_setting(self, key: str) -> Optional[SettingDatabase]:
        from restai.utils.crypto import SETTINGS_ENCRYPTED_KEYS, decrypt_field
        row = self.db.query(SettingDatabase).filter(SettingDatabase.key == key).first()
        if row and key in SETTINGS_ENCRYPTED_KEYS and row.value:
            self.db.expunge(row)
            row.value = decrypt_field(row.value)
        return row

    def get_setting_value(self, key: str, default: str = "") -> str:
        row = self.get_setting(key)
        return row.value if row and row.value else default

    def upsert_setting(self, key: str, value: str) -> None:
        from restai.utils.crypto import SETTINGS_ENCRYPTED_KEYS, encrypt_field
        stored_value = encrypt_field(value) if (key in SETTINGS_ENCRYPTED_KEYS and value) else value
        existing = self.db.query(SettingDatabase).filter(SettingDatabase.key == key).first()
        if existing:
            existing.value = stored_value
        else:
            self.db.add(SettingDatabase(key=key, value=stored_value))
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
