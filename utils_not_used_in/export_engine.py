import pathlib
import platform

if platform.system() == 'Windows':
    pathlib.PosixPath = pathlib.WindowsPath

from ultralytics import YOLO

model = YOLO("ModelHN_240326_03_Yolo26s_150526_01.pt")
model.export(format="engine", device=0, half=True, dynamic=True, batch=24, imgsz=[480, 640])