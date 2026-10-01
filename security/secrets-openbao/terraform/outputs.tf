output "openbao_vms" {
  description = "Public VM identities; no credentials are returned."
  value = {
    for name, vm in module.openbao_vm : name => {
      vm_id     = vm.vm_id
      node_name = vm.node_name
      address   = var.openbao_nodes[name].address
    }
  }
}

output "next_gate" {
  value = "Verify VM consoles and SSH host fingerprints before setting start_after_create=true or running Ansible."
}

