project_id      = "project-astrarome"
region          = "us-central1"
zone            = "us-central1-a"
billing_account = "01A1F8-00F06E-B378EB"
alert_emails    = ["thomas.hossler@gmail.com", "QalbalHayya@gmail.com"]

# 5432 lets `gcloud compute start-iap-tunnel seeing-db 5432` reach Postgres from a laptop
# (infra/scripts/run_local.py). Reset the VM after changing this.
iap_tcp_ports = ["22", "5432"]
