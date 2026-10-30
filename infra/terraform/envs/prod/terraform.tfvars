env = "prod"

# seeingthesky.com, behind IAP (iap_members only) like dev for now. Set web_public = true to open
# it to everyone (the app has its own accounts; sign-up is then open to the public).
web_public     = false
custom_domains = ["seeingthesky.com", "www.seeingthesky.com"]

# E-mail confirmation of new accounts (Brevo). First add the API key to the brevo-api-key-prod secret
# (gcloud secrets versions add), then set it to true. Sender and links: see variables.tf.
email_verification = false

iap_members = [
  "user:thomas.hossler@gmail.com",
  "user:QalbalHayya@gmail.com",
]

# Every hour at :45. The 00/06/12/18 UTC AROME cycles are usually published ~2h50, ~5h15, ~3h55 and ~5h25
# after the cycle; a late one is then computed at most an hour after it appears. A firing with nothing new
# exits in under a second (a run being computed by another execution is left alone). The monitors are
# collected once a day, at the 11h45 UTC firing (MONITORS_UTC_HOUR).
batch_schedule = "45 * * * *"

# Measured: ~364 MB RSS + at most 2 GRIB files (<= 1.6 GB) on the in-memory disk.
batch_cpu    = "2"
batch_memory = "4Gi"

deletion_protection = true
