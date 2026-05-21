import numpy as np
import cv2
import threading
import re

class BoundingBoxDrawerFFmpeg:
    def __init__(self, rtsp_url, width, height, frame_size, window_name):
        self.rtsp_url = rtsp_url
        self.width = width
        self.height = height
        self.frame_size = frame_size
        self.window_name = window_name
        self.drawing = False
        self.ix, self.iy = -1, -1
        self.start_point = None
        self.end_point = None
        self.boxes = []

    def draw_rectangle(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.ix, self.iy = x, y
            self.start_point = (x, y)

        elif event == cv2.EVENT_MOUSEMOVE:
            if self.drawing:
                self.end_point = (x, y)

        elif event == cv2.EVENT_LBUTTONUP:
            self.drawing = False
            self.end_point = (x, y)
            self.boxes.append((self.ix, self.iy, x, y))
            print(f"[{self.window_name}] Bounding Box: Start({self.ix}, {self.iy}), End({x}, {y})")
            print(f"[{self.window_name}] Width: {abs(x - self.ix)}, Height: {abs(y - self.iy)}")
            print(f"[{self.window_name}] Copy: {self.ix}, {self.iy}, {abs(x - self.ix)}, {abs(y - self.iy)}")

    def run(self):
        # Sử dụng cv2.VideoCapture thay vì FFmpeg
        cap = cv2.VideoCapture(self.rtsp_url)
        
        if not cap.isOpened():
            print(f"[{self.window_name}] ❌ Không thể kết nối đến stream: {self.rtsp_url}")
            return
        
        # Tự động lấy resolution từ stream
        self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[{self.window_name}] ✅ Kết nối thành công! Resolution: {self.width}x{self.height}")
        
        cv2.namedWindow(self.window_name)
        cv2.setMouseCallback(self.window_name, self.draw_rectangle)

        while True:
            ret, frame = cap.read()
            if not ret:
                print(f"[{self.window_name}] ⚠️ Không đọc được frame. Có thể mất kết nối.")
                break

            img = frame.copy()

            for box in self.boxes:
                cv2.rectangle(img, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)

            if self.drawing and self.start_point and self.end_point:
                cv2.rectangle(img, self.start_point, self.end_point, (0, 0, 255), 2)

            cv2.imshow(self.window_name, img)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyWindow(self.window_name)

def main():
    rtsp_urls = [
        # "rtsp://admin:Thado12@@192.168.1.131:554/Streaming/Channels/102",
        # "rtsp://admin:Thado12@@192.168.1.174:554/Streaming/Channels/102",
        # "rtsp://admin:Thado12@@192.168.1.187:554/Streaming/Channels/102",
        # "rtsp://admin:Thado12@@192.168.1.134:554/Streaming/Channels/102",
        # "rtsp://admin:Thado12@@192.168.1.173:554/Streaming/Channels/102",
        # "rtsp://admin:Thado12@@192.168.1.181:554/Streaming/Channels/102",
        # "rtsp://admin:Thado12@@192.168.1.182:554/Streaming/Channels/102",
        "rtsp://admin:Thado12@@192.168.1.146:554/Streaming/Channels/102",
        #"rtsp://127.0.0.1:8554/start"
    ]

    width, height = 640, 480  # Cập nhật theo độ phân giải camera thật
    frame_size = width * height * 3  # Tính frame_size

    threads = []
    for i, url in enumerate(rtsp_urls):
        match = re.search(r'\.(\d+):', url)
        cam_id = match.group(1) if match else "Unknown"

        window_name = f"Camera {cam_id}"
        drawer = BoundingBoxDrawerFFmpeg(url, width, height, frame_size, window_name)
        t = threading.Thread(target=drawer.run)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

if __name__ == "__main__":
    main()