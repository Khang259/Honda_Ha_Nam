import pathlib
import platform

if platform.system() == 'Windows':
    pathlib.PosixPath = pathlib.WindowsPath

from ultralytics import YOLO

model = YOLO("ModelHN_160326_02.pt")
model.export(format="engine", device=0, half=True, dynamic=True, batch=24, imgsz=[480, 640])