#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Own one disposable QEMU/KVM Omarchy VM under target/vm; no physical disks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import shutil
import socket
import subprocess
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
VM = ROOT / "target/vm"
LOCK = json.loads((ROOT / "tests/omarchy/image.lock.json").read_text())
PORT = 22280
DISK_BYTES = 64 * 1024**3


def private_json(path, value):
    path.write_text(json.dumps(value,indent=2)+"\n")
    path.chmod(0o600)


def prepare():
    VM.mkdir(parents=True,exist_ok=True)
    VM.chmod(0o700)
    (VM/"share").mkdir(exist_ok=True)
    access = VM/"access.json"
    if not access.exists():
        private_json(access,{"username":"memory","password":secrets.token_hex(12)})
    account = json.loads(access.read_text())
    key = VM/"ssh_key"
    if not key.exists():
        subprocess.run(["ssh-keygen","-q","-t","ed25519","-N","","-f",str(key)],check=True)
    seed = VM/"cidata"
    seed.mkdir(exist_ok=True,mode=0o700)
    size = lambda value:{"unit":"B","value":value,"sector_size":{"unit":"B","value":512}}
    boot_start,boot_size=1024**2,2*1024**3
    root_start=boot_start+boot_size
    partition = lambda **values:{"dev_path":None,"status":"create","type":"primary",**values}
    config = {
        "app_config":None,"archinstall-language":"English","auth_config":{},"audio_config":{"audio":"pipewire"},
        "bootloader_config":{"bootloader":"Limine","uki":False,"removable":False},"custom_commands":[],
        "omarchy_install":{"mode":"full_disk","defer_provisioning":False,"target_mount":"/mnt",
            "boot":{"esp_mount":"/boot","esp_path":"/EFI/limine","efi_binary":"limine_x64.efi","enable_fallback":True},"storage":{"kernel":"linux"}},
        "disk_config":{"config_type":"default_layout","device_modifications":[{"device":"/dev/vda","wipe":True,"partitions":[
            partition(btrfs=[],flags=["boot","esp"],fs_type="fat32",mount_options=[],mountpoint="/boot",obj_id="ea21d3f2-82bb-49cc-ab5d-6f81ae94e18d",size=size(boot_size),start=size(boot_start)),
            partition(btrfs=[{"mountpoint":p,"name":n} for p,n in (("/","@"),("/home","@home"),("/var/log","@log"),("/var/cache/pacman/pkg","@pkg"))],flags=[],fs_type="btrfs",mount_options=["compress=zstd"],mountpoint=None,obj_id="8c2c2b92-1070-455d-b76a-56263bab24aa",size=size(DISK_BYTES-root_start-1024**2),start=size(root_start)),
        ]}]},
        "hostname":"hyphae-omarchy-qa","kernels":["linux"],"network_config":{"type":"iso"},"ntp":True,"parallel_downloads":8,
        "script":None,"services":[],"swap":True,"timezone":"America/Bogota",
        "locale_config":{"kb_layout":"us","sys_enc":"UTF-8","sys_lang":"en_US.UTF-8"},
        "mirror_config":{"custom_repositories":[],"custom_servers":[{"url":"https://mirror.omarchy.org/$repo/os/$arch"},{"url":"https://geo.mirror.pkgbuild.com/$repo/os/$arch"}],"mirror_regions":{},"optional_repositories":[]},
        "packages":["base-devel","git","omarchy-keyring","omarchy-settings","omarchy"],"profile_config":{"gfx_driver":None,"greeter":None,"profile":{}},"version":"3.0.9",
    }
    password_hash = subprocess.check_output(["openssl","passwd","-6","-stdin"],input=(account["password"]+"\n").encode()).decode().strip()
    private_json(seed/"user_configuration.json",config)
    private_json(seed/"user_credentials.json",{"root_enc_password":password_hash,"users":[{"username":account["username"],"enc_password":password_hash,"groups":[],"sudo":True}]})
    (seed/"authorized_keys").write_text((VM/"ssh_key.pub").read_text())
    (seed/"user_full_name.txt").write_text("Hyphae Memory QA\n")
    (seed/"user_email_address.txt").write_text("memory-qa@example.invalid\n")
    (seed/"user_encrypt_installation.txt").write_text("false\n")
    subprocess.run(["genisoimage","-quiet","-output",str(VM/"cidata.iso"),"-volid","cidata","-joliet","-rock",str(seed)],check=True)
    if not (VM/"disk.qcow2").exists():
        subprocess.run(["qemu-img","create","-f","qcow2",str(VM/"disk.qcow2"),str(DISK_BYTES)],check=True)
    if not (VM/"OVMF_VARS.fd").exists():
        shutil.copyfile("/usr/share/edk2/ovmf/OVMF_VARS.fd",VM/"OVMF_VARS.fd")
    print(json.dumps({"status":"prepared","disk":str(VM/"disk.qcow2"),"memory_mib":6144,"cpus":4,"ssh_port":PORT}))


class Qmp:
    def __enter__(self):
        self.socket=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.socket.settimeout(10)
        self.socket.connect(str(VM/"qmp.sock"))
        self.stream=self.socket.makefile("rwb",buffering=0)
        json.loads(self.stream.readline())
        self.call("qmp_capabilities")
        return self
    def call(self,name,arguments=None):
        self.stream.write(json.dumps({"execute":name,"arguments":arguments or {}}).encode()+b"\n")
        while True:
            message=json.loads(self.stream.readline())
            if "error" in message: raise RuntimeError(message["error"])
            if "return" in message: return message["return"]
    def __exit__(self,*args):
        self.stream.close(); self.socket.close()


def start():
    if (VM/"qmp.sock").exists():
        try:
            with Qmp() as monitor:
                print(json.dumps(monitor.call("query-status"))); return
        except (OSError,ValueError):
            (VM/"qmp.sock").unlink()
    image=VM/f"omarchy-{LOCK['version']}.iso"
    with image.open("rb") as source:
        if image.stat().st_size != LOCK["bytes"] or hashlib.file_digest(source,"sha256").hexdigest() != LOCK["sha256"]:
            raise RuntimeError("Download and verify the pinned Omarchy ISO first.")
    command=["qemu-system-x86_64","-name","hyphae-omarchy-qa","-machine","q35,accel=kvm","-cpu","host","-smp","4","-m","6144",
        "-drive","if=pflash,format=raw,readonly=on,file=/usr/share/edk2/ovmf/OVMF_CODE.fd",
        "-drive",f"if=pflash,format=raw,file={VM/'OVMF_VARS.fd'}",
        "-drive",f"file={VM/'disk.qcow2'},if=virtio,format=qcow2,discard=unmap",
        "-drive",f"file={image},media=cdrom,readonly=on",
        "-drive",f"file={VM/'cidata.iso'},media=cdrom,readonly=on",
        "-boot","order=cd,menu=on","-device","virtio-vga","-display","none",
        "-qmp",f"unix:{VM/'qmp.sock'},server=on,wait=off","-serial",f"file:{VM/'serial.log'}",
        "-vnc",f"unix:{VM/'vnc.sock'}","-netdev",f"user,id=net0,hostfwd=tcp:127.0.0.1:{PORT}-:22","-device","virtio-net-pci,netdev=net0",
        "-fsdev",f"local,id=share,path={VM/'share'},security_model=none,readonly=on","-device","virtio-9p-pci,fsdev=share,mount_tag=hyphae",
    ]
    with (VM/"qemu.log").open("ab") as output:
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=output,stderr=output,start_new_session=True)
    for _ in range(100):
        if process.poll() is not None: raise RuntimeError((VM/"qemu.log").read_text()[-2000:])
        if (VM/"qmp.sock").exists(): break
        time.sleep(.05)
    private_json(VM/"process.json",{"pid":process.pid,"command":command})
    print(json.dumps({"status":"started","pid":process.pid,"ssh_port":PORT}))

def ssh_command():
    account=json.loads((VM/"access.json").read_text())
    return ["ssh","-i",str(VM/"ssh_key"),"-p",str(PORT),"-o","IdentitiesOnly=yes","-o","BatchMode=yes","-o","ConnectTimeout=5","-o","StrictHostKeyChecking=accept-new","-o",f"UserKnownHostsFile={VM/'known_hosts'}",f"{account['username']}@127.0.0.1"]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation",choices=["prepare","start","status","screen","stop","key","login","ssh","reference","mount-share","click","type","eval"])
    parser.add_argument("arguments",nargs="*")
    args=parser.parse_args()
    if args.operation=="prepare": prepare(); return
    if args.operation=="start": start(); return
    if args.operation=="ssh":
        raise SystemExit(subprocess.call([*ssh_command(),*args.arguments]))
    if args.operation=="eval":
        raise SystemExit(subprocess.call([*ssh_command(),"hyprctl -i 0 eval "+shlex.quote(" ".join(args.arguments))]))
    if args.operation=="mount-share":
        account=json.loads((VM/"access.json").read_text())
        command="sudo -S -p '' sh -c 'mkdir -p /mnt/hyphae; mountpoint -q /mnt/hyphae || mount -t 9p -o trans=virtio,version=9p2000.L,ro hyphae /mnt/hyphae'"
        subprocess.run([*ssh_command(),command],input=account["password"]+"\n",text=True,check=True)
        print("Read-only project share mounted in the VM.")
        return
    if args.operation=="reference":
        archive=ROOT/"target/omarchy-reference.tar.gz"
        with archive.open("wb") as output:
            subprocess.run([*ssh_command(),"tar -C /usr/share/omarchy -czf - shell bin config default version"],stdout=output,check=True,timeout=60)
        destination=ROOT/"target/omarchy-reference"
        destination.mkdir(exist_ok=True)
        with tarfile.open(archive) as source:
            if sum(member.size for member in source.getmembers())>64*1024*1024:
                raise RuntimeError("Unexpected Omarchy reference size")
            source.extractall(destination,members=[member for member in source.getmembers() if member.isfile() or member.isdir()],filter="data")
        print(destination)
        return
    with Qmp() as monitor:
        if args.operation=="status": print(json.dumps(monitor.call("query-status")))
        elif args.operation=="screen":
            path=VM/"screen.png"
            monitor.call("screendump",{"filename":str(path),"format":"png"})
            print(path)
        elif args.operation=="stop": monitor.call("system_powerdown")
        elif args.operation=="key":
            monitor.call("send-key",{"keys":[{"type":"qcode","data":key} for key in args.arguments],"hold-time":50})
        elif args.operation=="click":
            x,y=map(int,args.arguments)
            if not (0<=x<=8192 and 0<=y<=8192):raise ValueError("Click is outside the QA display bound")
            dispatch=f'hl.dsp.cursor.move({{x={x}, y={y}}})'
            subprocess.run([*ssh_command(),"hyprctl -i 0 dispatch "+shlex.quote(dispatch)],check=True)
            time.sleep(.1)
            monitor.call("input-send-event",{"events":[{"type":"btn","data":{"down":True,"button":"left"}}]})
            time.sleep(.08)
            monitor.call("input-send-event",{"events":[{"type":"btn","data":{"down":False,"button":"left"}}]})
        elif args.operation=="type":
            text=" ".join(args.arguments)
            if len(text)>512 or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789 .-/" for character in text):raise ValueError("QA typing accepts bounded lowercase ASCII text")
            for character in text:
                code={" ":"spc",".":"dot","-":"minus","/":"slash"}.get(character,character)
                monitor.call("send-key",{"keys":[{"type":"qcode","data":code}],"hold-time":10})
                time.sleep(.02)
        elif args.operation=="login":
            account=json.loads((VM/"access.json").read_text())
            if any(character not in "0123456789abcdef" for character in account["password"]):
                raise RuntimeError("The QA password must use its generated hexadecimal format.")
            for character in account["password"]:
                monitor.call("send-key",{"keys":[{"type":"qcode","data":character}],"hold-time":20})
                time.sleep(.04)
            monitor.call("send-key",{"keys":[{"type":"qcode","data":"ret"}],"hold-time":50})
            print("QA login submitted.")


if __name__=="__main__": main()
