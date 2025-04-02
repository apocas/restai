import typer
from alembic.config import Config
from alembic import command

app = typer.Typer()

@app.command()
def upgrade():
    """Run database migrations to upgrade the database schema."""
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

@app.command()
def downgrade():
    """Run database migrations to downgrade the database schema."""
    alembic_cfg = Config("alembic.ini")
    command.downgrade(alembic_cfg, "-1")

if __name__ == "__main__":
    app() 