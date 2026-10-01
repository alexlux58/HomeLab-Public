# Offline: the provider is mocked, so these plans contact nothing.
#   tofu init -backend=false && tofu test

mock_provider "proxmox" {
  # The VM resource validates file_id as "<datastore>:iso/<file>".
  mock_resource "proxmox_download_file" {
    defaults = {
      id = "local:iso/ubuntu-24.04-cloudimg-20260814.img"
    }
  }
}

variables {
  proxmox_api_token = "mock"
  state_passphrase  = "offline-mock-state-encryption-only"
}

run "default_plan_creates_nothing" {
  command = plan

  assert {
    condition     = length(proxmox_virtual_environment_vm.guest) == 0
    error_message = "With no rebuild_guests the plan must be empty."
  }
  assert {
    condition     = length(terraform_data.rebuild_gate) == 0 && length(proxmox_download_file.ubuntu) == 0
    error_message = "No gate or image download without a selection."
  }
}

run "wrong_confirmation_is_refused" {
  command = plan

  variables {
    rebuild_guests       = ["netbox"]
    rebuild_confirmation = "yes"
    ssh_public_keys      = { netbox = ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMockKeyOnly test"] }
  }

  expect_failures = [terraform_data.rebuild_gate]
}

run "non_rebuildable_guest_is_refused" {
  command = plan

  variables {
    rebuild_guests       = ["eveng"]
    rebuild_confirmation = "REBUILD eveng FROM ZERO"
  }

  expect_failures = [terraform_data.rebuild_gate]
}

run "confirmed_rebuild_plans_one_guest_from_lab_yml" {
  command = plan

  variables {
    rebuild_guests       = ["netbox"]
    rebuild_confirmation = "REBUILD netbox FROM ZERO"
    ssh_public_keys      = { netbox = ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMockKeyOnly test"] }
  }

  assert {
    condition     = length(proxmox_virtual_environment_vm.guest) == 1
    error_message = "Exactly the selected guest is planned."
  }
  assert {
    condition     = proxmox_virtual_environment_vm.guest["netbox"].vm_id == 330
    error_message = "VMID comes from lab.yml."
  }
  assert {
    condition     = proxmox_virtual_environment_vm.guest["netbox"].network_device[0].mac_address == "52:54:00:00:00:00"
    error_message = "MAC comes from lab.yml."
  }
  assert {
    condition     = proxmox_virtual_environment_vm.guest["netbox"].on_boot == false && proxmox_virtual_environment_vm.guest["netbox"].started == false
    error_message = "A rebuilt guest never auto-boots or starts."
  }
  assert {
    condition     = proxmox_virtual_environment_vm.guest["netbox"].protection == true
    error_message = "Protection stays on."
  }
}
