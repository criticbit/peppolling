import os
from getpass import getpass

from peppolling import PeppolBookkeeping

def get_env_or_prompt(env_name, prompt_text):
    value = os.getenv(env_name)
    if value:
        return value
    return getpass(prompt_text + ": ")

def main():
    api_key = get_env_or_prompt("PEPPYRUS_API_KEY", "Enter your Peppyrus API key")

    bk = PeppolBookkeeping(
        peppol_api_key=api_key,
        peppol_endpoint="https://api.test.peppyrus.be/"
    )

    results = bk.receive_invoices()

    if not results:
        print("No invoices received")
        return

    for r in results:
        print("Imported:", r)

if __name__ == "__main__":
    main()
