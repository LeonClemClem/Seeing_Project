env = "prod"

# seeingthesky.com, behind IAP (iap_members only) like dev for now. Set web_public = true to open
# it to everyone (the app has its own accounts; sign-up is then open to the public).
web_public     = false
custom_domains = ["seeingthesky.com", "www.seeingthesky.com"]

iap_members = [
  "user:thomas.hossler@gmail.com",
  "user:QalbalHayya@gmail.com",
]

# 4x/day, after the 00/06/12/18 UTC AROME cycles are published (observed ~2h50, ~5h15, ~3h55,
# ~5h25 after the cycle). A run already stored exits in under a second, so early firings are cheap.
batch_schedule = "45 3,11,16,23 * * *"

# Measured: ~364 MB RSS + at most 2 GRIB files (<= 1.6 GB) on the in-memory disk.
batch_cpu    = "2"
batch_memory = "4Gi"

deletion_protection = true
