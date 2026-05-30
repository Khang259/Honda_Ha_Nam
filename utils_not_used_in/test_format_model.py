from ultralytics import YOLO
import pathlib
import platform

if platform.system() == 'Windows':
    pathlib.PosixPath = pathlib.WindowsPath

model = YOLO("models/Third_try.engine", task="detect", verbose=False)          # hoặc yolov8s.engine, yolov8s_openvino_model/, v.v.

# Cách 1: Xem dtype của weights (chính xác nhất)
print(model.model)                  # in toàn bộ model structure
print(next(model.model.parameters()).dtype)  # thường là torch.float32 hoặc torch.float16

# Cách 2: Kiểm tra khi inference
results = model("images/192.168.1.101_01_20260204160731965.jpg", device="cuda")
print(results[0].boxes.data.dtype)   # dtype của output boxes (thường theo model dtype)

# Cách 3: Khi export đã biết
# Nếu bạn export bằng lệnh:
# yolo export model=yolov8s.pt format=engine half=True  → FP16
# yolo export model=yolov8s.pt format=engine int8=True  → INT8