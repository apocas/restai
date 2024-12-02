import paramiko
from typing import Dict, Any
import os
import config

#WARNING: Using containerssh.io or similar is recommended for (many) security reasons

def terminal(
    command: str, **load_kwargs: Dict[str, Any]
) -> bool:
    """
    Run a non-interactive linux command and get its output. Use this as a terminal.

    Args:
        command (str): Command to be executed.
    """
    
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(os.environ.get("RESTAI_RUNNER_HOST"), username=os.environ.get("RESTAI_RUNNER_USER"), password=os.environ.get("RESTAI_RUNNER_PASSWORD"), port=int(os.environ.get("RESTAI_RUNNER_PORT")), timeout=15)

    stdin, stdout, stderr = client.exec_command(command)
    output = stdout.read().decode()
    error = stderr.read().decode()

    client.close()
    
    full_output = output + error

    return full_output
