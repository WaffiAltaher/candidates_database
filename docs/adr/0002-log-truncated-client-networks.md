# Log truncated client networks, never full IP addresses

We want to see how the system is used: who logs in, how often, and from which area and country. We log and store only the client network (IPv4 /24, IPv6 /48) and the country derived from it, never the full IP address. The purpose is usage statistics, and the GDPR requires data minimisation. A /24 geolocates to a country almost as well as the full address, so the full address adds little information.

## Considered Options

- Full IP in the 7-day logs only: harder to justify under minimisation and the legitimate-interest balancing test, for barely more information than the network.
- Keyed hash of the IP: pseudonymous, but gives no location and needs a rotating secret.

## Consequences

- The truncation happens in the app (`candidates/client_network.py`); the full address only lives in memory during the request.
- A single device cannot be told apart from others on the same network.
- Users are told about the logging on the login page, see `docs/usage-logging.md`.
