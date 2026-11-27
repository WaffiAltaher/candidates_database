# Non-secret production values. CI loads this file automatically.
# Secrets stay in the GitHub environment "production", not in this file.
app_hostname   = "candidates.ittopia.nl"
allowed_origin = "https://candidates.ittopia.nl"

# Image tag that production runs. The Build image workflow opens a PR that
# sets this to the commit SHA it built. Never set it to a tag that has not
# been pushed: the Deploy workflow refuses to run in that case.
image_tag = "f6c3aff0d0d0eba36f581d0674e0ac21a56d06b9"
