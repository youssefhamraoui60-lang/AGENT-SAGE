"""Create a dedicated Windows-user SSH key; never overwrite an existing key."""
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
key=Path.home()/'.ssh'/'agent_sage_vm_ed25519'
key.parent.mkdir(exist_ok=True)
if not key.exists():
    subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-C','agent-sage-x3-vm','-f',str(key)],check=True)
public=Path(str(key)+'.pub').read_text(encoding='utf-8').strip()
(root/'docker/vm-authorized-key.pub').write_text(public+'\n',encoding='utf-8')
(root/'docker/vm-cloud-init.yaml').write_text(
    '#cloud-config\nhostname: agent-sage-docker\nmanage_etc_hosts: true\nusers:\n  - default\n'
    f'ssh_authorized_keys:\n  - {public}\nssh_pwauth: false\ndisable_root: true\n',encoding='utf-8')
(root/'docker/vm-meta-data').write_text('instance-id: agent-sage-docker-01\nlocal-hostname: agent-sage-docker\n',encoding='utf-8')
print('Dedicated public key and optional cloud-init files prepared. Private key stays in the Windows user profile.')
