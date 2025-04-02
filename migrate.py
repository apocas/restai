import typer
from alembic.config import Config
from alembic import command
from restai.config import POSTGRES_URL, MYSQL_URL, POSTGRES_HOST, MYSQL_HOST

app = typer.Typer()

def get_database_url():
    if POSTGRES_HOST:
        return POSTGRES_URL
    elif MYSQL_HOST:
        return MYSQL_URL
    else:
        return "sqlite:///./restai.db"

@app.command()
def upgrade():
    """Run database migrations to upgrade the database schema."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", get_database_url())
    command.upgrade(alembic_cfg, "head")

@app.command()
def downgrade():
    """Run database migrations to downgrade the database schema."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", get_database_url())
    command.downgrade(alembic_cfg, "-1")

if __name__ == "__main__":
    app() 