env = "prod"

iap_members = [
  "user:thomas.hossler@gmail.com",
  "user:QalbalHayya@gmail.com",
]

# 4x/day, ~4h30 after each 00/06/12/18 UTC AROME cycle (to be confirmed by the batch owner).
batch_schedule = "30 4,10,16,22 * * *"

# Sizing to be confirmed by the batch owner (8Gi needs >= 2 vCPU on Cloud Run).
batch_cpu    = "2"
batch_memory = "8Gi"

deletion_protection = true
