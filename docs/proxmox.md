# Proxmox power buttons

With the `proxmox` plugin, VMs and containers get **Start**, **Shut down** and
**Reboot** buttons. Shutting down or rebooting needs a second tap to confirm.
faro talks to the Proxmox API with a token that is only allowed to do that.

On each Proxmox node:

```sh
# a user and a role that can only power guests on and off
pveum user add faro@pve --comment "faro dashboard"
pveum role add FaroPower --privs "VM.PowerMgmt VM.Audit"
pveum acl modify /vms --users faro@pve --roles FaroPower
# a token for that user (privilege separation off: it inherits exactly the role above)
pveum user token add faro@pve faro --privsep 0
```

Copy the token secret it prints (you'll only see it once) and give it to faro
without putting it in the config:

```sh
echo 'faro@pve!faro=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' | sudo install -m 600 -o faro /dev/stdin /etc/faro/pve1-token
```

```toml
[[hosts]]
id = "pve1"
address = "192.168.1.10"
api_token = "file:/etc/faro/pve1-token"

[plugins.proxmox]
```

The token can't read disks, change configuration, open consoles or touch the host.
