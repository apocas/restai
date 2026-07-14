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
    try:
        client.connect(host, username=username, password=password, port=port,
                       timeout=15, allow_agent=False, look_for_keys=False)
    except paramiko.AuthenticationException:
        return "ERROR: SSH authentication failed."
    except Exception as e:
        # connect() runs BEFORE the exec try/except and raises many uncaught
        # types on failure — TimeoutError (unreachable), socket.gaierror (bad
        # DNS), ConnectionRefusedError, paramiko.SSHException (negotiation) —
        # none of which the agent runtime's TypeError-only guard catches, so an
        # unreachable host would otherwise crash the tool call. Return a clean
        # ERROR string like the rest of the tool.
        return f"ERROR: SSH connection to {host}:{port} failed: {e}"

    try:
        stdin, stdout, stderr = client.exec_command(command)
        channel = stdout.channel
        channel.settimeout(30)
        output = stdout.read().decode(errors="replace")
        error = stderr.read().decode(errors="replace")
    except (socket.timeout, paramiko.SSHException):
        client.close()
        return "ERROR: Command timeout"

    client.close()
    return output + error
