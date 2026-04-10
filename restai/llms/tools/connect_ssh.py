import paramiko
import socket


def connect_ssh(
    command: str,
    host: str,
    port: int = 22,
    username: str = "root",
    password: str = "",
) -> str:
    """
    Connect to a remote host via SSH and execute a non-interactive linux command.

    Args:
        command (str): Command to be executed on the remote host.
        host (str): Hostname or IP to connect to.
        port (int): SSH port.
        username (str): SSH username.
        password (str): SSH password.
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=username, password=password, port=port,
                   timeout=15, allow_agent=False, look_for_keys=False)

    try:
        stdin, stdout, stderr = client.exec_command(command)
        channel = stdout.channel
        channel.settimeout(30)
        output = stdout.read().decode()
        error = stderr.read().decode()
    except (socket.timeout, paramiko.SSHException):
        client.close()
        return "ERROR: Command timeout"

    client.close()
    return output + error
