# workstation Plex implementation plan

Prepared 2026-09-28. Plex was selected as the next workstation workload. Plex Media Server 1.43.4.10903 is now installed and responds locally; the NAS library and client validation remain pending.

## Verified starting state

- Windows 11 Home, Ryzen 7 2700X, 31.91 GiB RAM, GTX 1080. Free RAM was only 3.99 GiB during an active game session; measure again when idle before testing transcoding.
- Before installation, no Plex installation, TCP/32400 listener, Plex firewall rule, mapped SMB share, or media directory was found locally. The installer added four broad inbound rules, which were disabled after the operator's explicit approval. The local listener now works at `http://127.0.0.1:32400/web`.
- workstation is `192.168.0.70` on Ethernet. Windows marks this network **Public**, and all firewall profiles are enabled.
- The operator selected a new `Media` shared folder on NAS Volume 2 with a 2 TB quota. The shared folder was created through Synology CLI on 2026-09-29; the 2 TB quota and dedicated read-only `plex-reader` account still need to be set in DSM. The first playback client remains to be identified.

## Proposed single-host design

1. Install the official **Plex Media Server for Windows** under the normal desktop account. Plex will be available only while Windows and that user session are active; the desktop's existing sleep behavior remains in force.
2. Keep media on one specified NAS SMB share and point Plex libraries to its UNC path. Give the account used by Plex read/execute access only. Do not copy media into the project or put NAS credentials in scripts, this repository, or the Plex library path. Plex's [network-resource guide](https://support.plex.tv/articles/201122318-mounting-network-resources/) supports UNC paths on Windows; its [permission guide](https://support.plex.tv/articles/201543057-why-is-some-of-my-content-not-found/) requires the Plex process account to read the media.
3. Claim the server in the local web app at `http://127.0.0.1:32400/web` through the operator's browser session. Leave remote access disabled, leave the unauthenticated-network allowlist empty, and disable DLNA unless a named client requires it. [Plex installation](https://support.plex.tv/articles/200288586-installation/) and [LAN authentication](https://support.plex.tv/articles/200890058-authentication-for-local-network-access/) describe these controls.
4. Allow inbound **TCP/32400** in Windows Firewall only from the first approved LAN client, on Ethernet, after its IP is known. The rule must be precise even though Ethernet currently uses the Public profile. No router port forwarding, UPnP mapping, VPN listener, or public tunnel is part of this phase. Plex identifies TCP/32400 as its [required server port](https://support.plex.tv/articles/201543147-what-network-ports-do-i-need-to-allow-through-my-firewall/).
5. Keep Plex metadata in its default `%LOCALAPPDATA%\Plex Media Server` directory initially and back up that directory separately from the NAS media. [Plex's Windows data-directory reference](https://support.plex.tv/articles/202915258-where-is-the-plex-media-server-data-directory-located/) documents the path.
6. Start with Direct Play. Test one representative software transcode only when no game is running and RAM has headroom. Hardware acceleration needs a confirmed Plex Pass entitlement and a measured GTX 1080 test; see [Plex hardware-accelerated streaming](https://support.plex.tv/articles/115002178853-using-hardware-accelerated-streaming/).

## Concrete implementation gate

The operator created `Media` on Volume 2 through the Synology CLI. The operator must still set the 2 TB shared-folder quota through DSM and create a dedicated read-only `plex-reader` account. NAS admin authentication is required; the agent may not handle the password, and browser control of DSM was denied. After creation, verify the share and reader access, connect Windows to `\\192.168.0.20\Media` using credentials entered privately by the operator, and add Plex libraries using UNC paths. The first playback client's type and IP, Plex Pass entitlement, and one owned test file remain unknown. With these details, document the client-scoped firewall rule and finish the Plex phase.

Acceptance: local web app opens (**verified**); the selected share is readable without write access; a test item appears; the selected client plays by Direct Play over LAN; one intentional software transcode is measured if suitable media exists; remote access is off; the firewall rule permits only the approved client; and metadata backup has a restore path. Until the NAS share exists, library/playback acceptance stays pending.

Rollback: stop Plex, remove its one scoped firewall rule, remove the library mapping or NAS access, and uninstall Plex if required. Preserve the Plex metadata backup and NAS media; no NAS content or backup archive should be deleted.
