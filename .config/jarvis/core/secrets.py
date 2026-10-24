"""
Secrets for later integrations live in gnome-keyring (libsecret), never in files
tracked by `stark`. Nothing uses this yet: Claude authenticates through the
claude CLI login, so there are no API keys.

    store("govee-cloud", "api-key")     # prompts on stdin, saves to the keyring
    get("govee-cloud", "api-key")       # → str | None
"""
import getpass
import subprocess

ATTR = "jarvis"


def get(service, account):
    p = subprocess.run(["secret-tool", "lookup", ATTR, service, "account", account],
                       capture_output=True, text=True)
    return p.stdout.rstrip("\n") if p.returncode == 0 and p.stdout else None


def store(service, account, value=None):
    value = value if value is not None else getpass.getpass(f"{service} {account}: ")
    subprocess.run(["secret-tool", "store", "--label", f"Jarvis: {service} {account}",
                    ATTR, service, "account", account], input=value, text=True, check=True)


def delete(service, account):
    subprocess.run(["secret-tool", "clear", ATTR, service, "account", account], check=False)
