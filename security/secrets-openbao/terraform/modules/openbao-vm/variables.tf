variable "name" { type = string }
variable "vm_id" { type = number }
variable "node_name" { type = string }
variable "address" { type = string }
variable "mac_address" { type = string }
variable "disk_datastore" { type = string }
variable "disk_format" { type = string }
variable "disk_ssd" { type = bool }
variable "cloud_image_file_id" { type = string }
variable "gateway" { type = string }
variable "dns_server" { type = string }
variable "dns_domain" { type = string }
variable "description" { type = string }
variable "ssh_public_keys" { type = list(string) }
variable "started" { type = bool }

