"""TM1 server connectivity: connection profiles, credentials, session setup.

Split three ways so each piece stays testable on its own:

- :mod:`linti.tm1.connections` — the profile file. Non-secret data only.
- :mod:`linti.tm1.credentials` — where the password comes from, and nowhere else.
- :mod:`linti.tm1.service` — the only module in linti that imports TM1py.
"""
