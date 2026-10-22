# Serve the frontend from the API container

The frontend was a bucket website, which serves only plain HTTP on a custom domain and cannot set response headers. We serve `frontend/` from the FastAPI container instead and bind `candidates.ittopia.nl` to the container with a Scaleway custom domain, which gets a free, auto-renewed Let's Encrypt certificate. The frontend and API then share one origin and ship in one image.

## Considered Options

- Scaleway Edge Services in front of the bucket: paid subscription, still two deploy steps, no control over page headers.
- Cloudflare proxy: requires moving the `ittopia.nl` DNS zone off Route 53.

## Consequences

- The first page load after the container scales to zero waits for a cold start.
- The CNAME must point at the container before the custom domain is created, or the HTTP-01 challenge fails and the domain goes to `error`.
- The frontend bucket stays in Terraform, unused, until a separate cleanup removes it.
