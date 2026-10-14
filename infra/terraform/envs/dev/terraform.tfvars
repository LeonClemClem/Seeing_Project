env = "dev"

iap_members = [
  "user:thomas.hossler@gmail.com",
  "user:QalbalHayya@gmail.com",
]

# Once a day, after the 00 UTC AROME cycle is published (to be confirmed by the batch owner).
batch_schedule = "0 5 * * *"

# Dev can be destroyed freely.
deletion_protection = false
