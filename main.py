from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
import os
import subprocess
import shutil

app = FastAPI(title = "Мини-облачный провайдер")
SUPPORTED_FS = ["ext4", "xfs", "btrfs"] 
class CreateDisk(BaseModel):
    size_mb: int
    fs_type: str = "ext4"

class ResponseDisk(BaseModel):
    name: str
    size_mb: int
    fs_type: str 
    mounted: bool
    mount_point: str | None = None

disks_db = {}
DISKS_DIR = "disks_images"
os.makedirs(DISKS_DIR, exist_ok=True)
@app.get("/")
def root():
    return {"message": "Мини-облачный провайдер работает!"}

@app.get("/disks/{disk_name}")
def get_disk(disk_name: str):
    if disk_name not in disks_db:
        return {"error": f"диск {disk_name} не найден"}
    return disks_db[disk_name]


@app.get("/disks")
def list_disks():
    return list(disks_db.values())

@app.post("/disks/{disk_name}", response_model = ResponseDisk)
def create_disk(disk_name: str, disk: CreateDisk):
    if disk_name in disks_db:
        #идемпотентность 
        return disks_db[disk_name]
    
    if disk.fs_type not in SUPPORTED_FS:
        return {"error": f"Неподдерживаемая ФС: {disk.fs_type}. Поддерживаются: {SUPPORTED_FS}"}

    disk_path = os.path.join(DISKS_DIR, f"{disk_name}.img")
   
    try:
        subprocess.run(
            ["dd", "if=/dev/zero",f"of={disk_path}", "bs=1M", f"count={disk.size_mb}"],
            check=True,
            capture_output=True,
            text=True,

        )
        if disk.fs_type == "xfs":
            subprocess.run(
                ["mkfs.xfs", "-f", disk_path], 
                check=True,
                capture_output=True,
                text=True,
            )
        elif disk.fs_type == "btrfs":
            subprocess.run(
                ["mkfs.btrfs", "-f", disk_path],
                check=True,
                capture_output=True,
                text=True,
            )
        else:
            subprocess.run(
                ["mkfs", "-t", disk.fs_type, "-F", disk_path],
                check=True,
                capture_output=True,
                text=True,
            )
    except subprocess.CalledProcessError as e:
        if os.path.exists(disk_path):
            os.remove(disk_path)
        return {"error": f"Ошибка создания диска: {e.stderr}"}

    new_disk = {
        "name": disk_name,
        "size_mb": disk.size_mb,
        "fs_type": disk.fs_type,
        "mounted": False,
        "mount_point": None,
        "path": disk_path

    }
    disks_db[disk_name] = new_disk
    return new_disk

@app.post("/disks/{disk_name}/mount")
def mount_disk(disk_name: str, mount_point: str = None):
    if disk_name not in disks_db:
        return {"error": f"диск {disk_name} не найден"}
    
    disk =disks_db[disk_name]
    if disk["mounted"]:
        return {"error": "диск уже смонтирован"}
    
    if not mount_point:
        mount_point = f"/mnt/{disk_name}"

    os.makedirs(mount_point, exist_ok=True)

    try:
        subprocess.run(
            ["mount", "-o", "loop", disk["path"], mount_point],
            check=True,
            capture_output=True,
            text=True
        )
        disk["mounted"] = True
        disk["mount_point"] = mount_point
        return {"message": f"диск {disk_name} примонтирован в {mount_point}"}
    except subprocess.CalledProcessError as e:
        return {"error": f"ошибка монтирования: {e.stderr}"}

@app.post("/disks/{disk_name}/umount")
def umount_disk(disk_name: str):
    if disk_name not in disks_db:
        return {"error": f"диск {disk_name} не найден"}
    disk =disks_db[disk_name]
    if not disk["mounted"]:
        return {"error": "диск не смонтирован"}
    
    try:
        subprocess.run(
            ["umount",  disk["mount_point"]],
            check=True,
            capture_output=True,
            text=True
        )
        disk["mounted"] = False
        disk["mount_point"] = None
        return {"message": f"диск {disk_name} размонтирован"}
    except subprocess.CalledProcessError as e:
        return {"error": f"ошибка размонтирования: {e.stderr}"}


@app.delete("/disks/{disk_name}")
def delete_disk(disk_name: str):
    if disk_name not in disks_db:
        return {"message": f"диск {disk_name} уже удален"}
    
    disk =disks_db[disk_name]
    if disk["mounted"]:
        try:
            subprocess.run(["umount", disk["mount_point"]], check=True)
        except:
            pass

    try:
        if os.path.exists(disk["path"]):
            os.remove(disk["path"])
    except Exception as e:
        return{"error": f"ошибка удаления файла: {e}"}
           
    del disks_db[disk_name]
    return {"message": f"диск {disk_name} удален "}



@app.get("/metrics")
def get_metrics():
    total_disks = len(disks_db)
    total_size_mb = sum(d["size_mb"] for d in disks_db.values())
    mounted_count = sum(1 for d in disks_db.values() if d["mounted"])
    d_usage = shutil.disk_usage(DISKS_DIR)
    free_space_mb = d_usage.free // (1024 * 1024)

    return {
        "total_disks": total_disks,
        "total_size_mb" : total_size_mb,
        "mounted_disks" : mounted_count,
        "free_space_mb": free_space_mb
    }


if __name__ == "__main__":
    uvicorn.run(app, host ="0.0.0.0", port = 8000)