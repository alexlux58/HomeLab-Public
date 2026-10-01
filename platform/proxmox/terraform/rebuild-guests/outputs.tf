output "selected_guests" {
  description = "Guests this plan would create, with their identities from lab.yml."
  value = {
    for name, guest in local.selected : name => {
      vmid    = guest.vmid
      node    = guest.node
      address = guest.address
      mac     = guest.mac
    }
  }
}
